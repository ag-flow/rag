from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib.parse import urlencode

import asyncpg
import httpx
import structlog
from joserfc import jwt as joserfc_jwt
from joserfc._keys import KeySetSerialization
from joserfc.errors import BadSignatureError, ExpiredTokenError, InvalidClaimError, JoseError
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry

from rag.api.errors import (
    OidcInvalidCode,
    OidcInvalidToken,
    OidcKeycloakUnreachable,
    OidcNotConfigured,
    OidcSessionExpired,
)

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


@dataclass(frozen=True)
class OidcConfig:
    """Config OIDC stockée en `oidc_config` (1 row max)."""

    issuer: str
    client_id: str
    client_secret_ref: str  # clé logique Harpocrate


@dataclass(frozen=True)
class _TokenPair:
    """Résultat d'un exchange code ou d'un refresh token."""

    id_token: str
    access_token: str
    refresh_token: str
    expires_at: int  # epoch seconds


@dataclass(frozen=True)
class _DiscoveryDoc:
    """Document OpenID Connect discovery (well-known), mis en cache TTL 1h."""

    authorization_endpoint: str
    token_endpoint: str
    end_session_endpoint: str
    jwks_uri: str
    fetched_at: float  # time.monotonic()


class OidcService:
    """Encapsule tout l'état OIDC : config DB, discovery + JWKS cache,
    code exchange, JWT verify, refresh, logout URL.

    Thread-safety : asyncio single-thread - pas de lock requis.
    """

    _DISCOVERY_TTL_SECONDS = 3600

    def __init__(
        self,
        *,
        config_pool: asyncpg.Pool,
        secret_resolver: _ResolverProtocol,
        public_url: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config_pool = config_pool
        self._secret_resolver = secret_resolver
        self._public_url = public_url.rstrip("/")
        self._http_client = http_client  # injection pour tests
        self._discovery_cache: dict[str, _DiscoveryDoc] = {}
        self._jwks_cache: dict[str, KeySet] = {}

    # --- CRUD config ---

    async def get_config(self) -> OidcConfig | None:
        row = await self._config_pool.fetchrow(
            "SELECT issuer, client_id, client_secret_ref FROM oidc_config LIMIT 1"
        )
        if row is None:
            return None
        return OidcConfig(
            issuer=row["issuer"],
            client_id=row["client_id"],
            client_secret_ref=row["client_secret_ref"],
        )

    async def upsert_config(
        self,
        *,
        issuer: str,
        client_id: str,
        client_secret_ref: str,
    ) -> OidcConfig:
        """Remplace toute config existante. Pattern : 1 row max en table.

        DELETE + INSERT en transaction. On garantit qu'il y a au plus 1 row
        à tout moment (pas de PK naturel, contrainte applicative).
        """
        async with self._config_pool.acquire() as conn, conn.transaction():
            await conn.execute("DELETE FROM oidc_config")
            await conn.execute(
                """
                INSERT INTO oidc_config (issuer, client_id, client_secret_ref)
                VALUES ($1, $2, $3)
                """,
                issuer,
                client_id,
                client_secret_ref,
            )
        log.info("oidc.config.upserted", issuer=issuer, client_id=client_id)
        return OidcConfig(
            issuer=issuer,
            client_id=client_id,
            client_secret_ref=client_secret_ref,
        )

    # --- Discovery + JWKS cache ---

    async def _discover(self, config: OidcConfig) -> _DiscoveryDoc:
        """Fetch ${issuer}/.well-known/openid-configuration et cache TTL 1h."""
        key = config.issuer
        cached = self._discovery_cache.get(key)
        if cached is not None and (
            time.monotonic() - cached.fetched_at < self._DISCOVERY_TTL_SECONDS
        ):
            return cached

        url = f"{config.issuer.rstrip('/')}/.well-known/openid-configuration"
        client = self._http_client or httpx.AsyncClient(timeout=10.0)
        owned_client = self._http_client is None
        try:
            try:
                resp = await client.get(url)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                raise OidcKeycloakUnreachable(config.issuer) from e
            if resp.status_code != 200:
                raise OidcKeycloakUnreachable(config.issuer)
            payload: dict[str, Any] = resp.json()
        finally:
            if owned_client:
                await client.aclose()

        doc = _DiscoveryDoc(
            authorization_endpoint=payload["authorization_endpoint"],
            token_endpoint=payload["token_endpoint"],
            end_session_endpoint=payload["end_session_endpoint"],
            jwks_uri=payload["jwks_uri"],
            fetched_at=time.monotonic(),
        )
        self._discovery_cache[key] = doc
        log.info("oidc.discovery.fetched", issuer=config.issuer)
        return doc

    async def _jwks(self, discovery: _DiscoveryDoc) -> KeySet:
        """Fetch + cache JWKS. Reload on signature fail handled by caller."""
        cached = self._jwks_cache.get(discovery.jwks_uri)
        if cached is not None:
            return cached

        client = self._http_client or httpx.AsyncClient(timeout=10.0)
        owned_client = self._http_client is None
        try:
            try:
                resp = await client.get(discovery.jwks_uri)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                raise OidcKeycloakUnreachable(discovery.jwks_uri) from e
            if resp.status_code != 200:
                raise OidcKeycloakUnreachable(discovery.jwks_uri)
            payload: dict[str, Any] = resp.json()
        finally:
            if owned_client:
                await client.aclose()

        keyset = KeySet.import_key_set(cast(KeySetSerialization, payload))
        self._jwks_cache[discovery.jwks_uri] = keyset
        log.info("oidc.jwks.fetched", jwks_uri=discovery.jwks_uri)
        return keyset

    # --- JWT verify + roles ---

    async def verify_id_token(
        self,
        id_token: str,
        *,
        config: OidcConfig,
    ) -> dict[str, Any]:
        """Vérifie signature (JWKS), iss, aud, exp.

        Raise OidcInvalidToken("expired") sur exp dépassé.
        Raise OidcInvalidToken("...") sur signature/iss/aud invalides.
        """
        discovery = await self._discover(config)
        keyset = await self._jwks(discovery)

        try:
            token = joserfc_jwt.decode(id_token, key=keyset, algorithms=["RS256"])
        except BadSignatureError as e:
            raise OidcInvalidToken("bad_signature") from e
        except JoseError as e:
            raise OidcInvalidToken(f"jose_error: {type(e).__name__}") from e

        registry = JWTClaimsRegistry(
            iss={"essential": True, "value": config.issuer},
            aud={"essential": True, "value": config.client_id},
            exp={"essential": True},
        )
        try:
            registry.validate(token.claims)
        except ExpiredTokenError as e:
            raise OidcInvalidToken("expired") from e
        except InvalidClaimError as e:
            raise OidcInvalidToken(f"invalid_claim:{e.claim}") from e
        except JoseError as e:
            raise OidcInvalidToken(f"jose_error: {type(e).__name__}") from e

        return dict(token.claims)

    def extract_roles(self, claims: dict[str, Any], client_id: str) -> list[str]:
        """Extrait `claims.resource_access.<client_id>.roles` ou []."""
        resource_access = claims.get("resource_access") or {}
        client_section = resource_access.get(client_id) or {}
        roles = client_section.get("roles") or []
        return list(roles)

    # --- Authorize + Logout URL ---

    async def build_authorize_url(self) -> tuple[str, str, str]:
        """Construit l'URL d'authorize Keycloak avec state + nonce aléatoires.

        Returns (url, state, nonce). Le caller stocke (state, nonce) dans
        un cookie éphémère (Starlette session) pour validation au callback.

        Raise OidcNotConfigured si aucune config OIDC en DB.
        """
        cfg = await self.get_config()
        if cfg is None:
            raise OidcNotConfigured()
        discovery = await self._discover(cfg)

        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        params = {
            "client_id": cfg.client_id,
            "redirect_uri": f"{self._public_url}/auth/callback",
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
        }
        url = f"{discovery.authorization_endpoint}?{urlencode(params)}"
        return url, state, nonce

    # --- Token exchange + refresh ---

    async def exchange_code(
        self,
        *,
        code: str,
        expected_nonce: str,
        config: OidcConfig,
    ) -> _TokenPair:
        """POST token_endpoint avec grant_type=authorization_code.

        Vérifie la signature + claims du id_token et contrôle le nonce.

        Raise OidcInvalidCode si Keycloak rejette le code.
        Raise OidcInvalidToken si nonce ne match pas.
        """
        return await self._token_request(
            config=config,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": f"{self._public_url}/auth/callback",
            },
            expected_nonce=expected_nonce,
        )

    async def refresh(
        self,
        *,
        refresh_token: str,
        config: OidcConfig,
    ) -> _TokenPair:
        """POST token_endpoint avec grant_type=refresh_token.

        Raise OidcSessionExpired si Keycloak rejette le refresh_token.
        """
        try:
            return await self._token_request(
                config=config,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                expected_nonce=None,
            )
        except OidcInvalidCode as e:
            raise OidcSessionExpired() from e

    async def _token_request(
        self,
        *,
        config: OidcConfig,
        data: dict[str, str],
        expected_nonce: str | None,
    ) -> _TokenPair:
        """Factorise l'appel POST au token_endpoint.

        Résout le client_secret via Harpocrate à chaque appel (actions peu
        fréquentes, pas de cache pour éviter de tenir un secret en mémoire).
        """
        discovery = await self._discover(config)
        client_secret = await self._secret_resolver.resolve_with_retry(
            f"${{vault://rag:{config.client_secret_ref}}}"
        )
        payload = {
            **data,
            "client_id": config.client_id,
            "client_secret": client_secret,
        }

        client = self._http_client or httpx.AsyncClient(timeout=10.0)
        owned_client = self._http_client is None
        try:
            resp = await client.post(discovery.token_endpoint, data=payload)
        finally:
            if owned_client:
                await client.aclose()

        if resp.status_code != 200:
            try:
                body: dict[str, Any] = resp.json()
                reason = body.get("error", f"http_{resp.status_code}")
            except Exception:
                reason = f"http_{resp.status_code}"
            raise OidcInvalidCode(str(reason))

        body = resp.json()
        id_token: str = body["id_token"]

        # Vérification nonce uniquement au callback (protection replay attacks).
        # Pour le refresh, Keycloak peut émettre un id_token sans nonce.
        if expected_nonce is not None:
            claims = await self.verify_id_token(id_token, config=config)
            if claims.get("nonce") != expected_nonce:
                raise OidcInvalidToken("nonce_mismatch")

        now = int(time.time())
        return _TokenPair(
            id_token=id_token,
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token", ""),
            expires_at=now + int(body.get("expires_in", 300)),
        )

    async def build_logout_url(self, *, id_token: str, config: OidcConfig) -> str:
        """Construit l'URL de logout Keycloak avec id_token_hint."""
        discovery = await self._discover(config)
        params = {
            "id_token_hint": id_token,
            "post_logout_redirect_uri": f"{self._public_url}/",
        }
        return f"{discovery.end_session_endpoint}?{urlencode(params)}"
