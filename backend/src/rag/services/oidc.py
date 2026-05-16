from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol, cast

import asyncpg
import httpx
import structlog
from joserfc._keys import KeySetSerialization
from joserfc.jwk import KeySet

from rag.api.errors import OidcKeycloakUnreachable

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    def resolve_with_retry(self, ref: str) -> str: ...


@dataclass(frozen=True)
class OidcConfig:
    """Config OIDC stockée en `oidc_config` (1 row max)."""

    issuer: str
    client_id: str
    client_secret_ref: str  # clé logique Harpocrate


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
