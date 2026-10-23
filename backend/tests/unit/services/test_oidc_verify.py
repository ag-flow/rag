from __future__ import annotations

import time
from typing import Any

import httpx
import pytest
from joserfc import jwt
from joserfc.jwk import RSAKey

from rag.api.errors import OidcInvalidToken
from rag.services.oidc import OidcConfig, OidcService

# Clé RSA partagée pour les tests : signe les JWT localement, expose la
# public part dans le JWKS mocké.
_RSA_KEY = RSAKey.generate_key(key_size=2048, private=True)
_KID = "test-key-id"


def _make_signed_jwt(claims: dict[str, Any]) -> str:
    header = {"alg": "RS256", "kid": _KID, "typ": "JWT"}
    return jwt.encode(header, claims, _RSA_KEY)


def _jwks_payload() -> dict:
    pub_dict = _RSA_KEY.as_dict(private=False)
    pub_dict["kid"] = _KID
    pub_dict["alg"] = "RS256"
    pub_dict["use"] = "sig"
    return {"keys": [pub_dict]}


def _discovery_payload(issuer: str) -> dict:
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/auth",
        "token_endpoint": f"{issuer}/token",
        "end_session_endpoint": f"{issuer}/logout",
        "jwks_uri": f"{issuer}/jwks",
    }


def _make_service(issuer: str, client_id: str = "rag-service") -> tuple[OidcService, OidcConfig]:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "well-known" in url:
            return httpx.Response(200, json=_discovery_payload(issuer))
        if "jwks" in url:
            return httpx.Response(200, json=_jwks_payload())
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    svc = OidcService(
        config_pool=None,
        public_url="https://rag.example.com",
        http_client=client,
    )
    cfg = OidcConfig(issuer=issuer, client_id=client_id)
    return svc, cfg


@pytest.mark.asyncio
async def test_verify_id_token_accepts_well_formed_jwt() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc, cfg = _make_service(issuer)
    now = int(time.time())
    claims = {
        "iss": issuer,
        "aud": "rag-service",
        "sub": "user-uuid",
        "exp": now + 300,
        "iat": now,
        "nonce": "test-nonce",
    }
    token = _make_signed_jwt(claims)
    decoded = await svc.verify_id_token(token, config=cfg)
    assert decoded["sub"] == "user-uuid"
    assert decoded["nonce"] == "test-nonce"


@pytest.mark.asyncio
async def test_verify_id_token_rejects_bad_signature() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc, cfg = _make_service(issuer)
    # Forge un token avec une AUTRE clé RSA
    other_key = RSAKey.generate_key(key_size=2048, private=True)
    header = {"alg": "RS256", "kid": _KID, "typ": "JWT"}
    claims = {
        "iss": issuer,
        "aud": "rag-service",
        "sub": "u",
        "exp": int(time.time()) + 300,
        "iat": int(time.time()),
    }
    forged = jwt.encode(header, claims, other_key)
    with pytest.raises(OidcInvalidToken):
        await svc.verify_id_token(forged, config=cfg)


@pytest.mark.asyncio
async def test_verify_id_token_rejects_expired() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc, cfg = _make_service(issuer)
    now = int(time.time())
    claims = {
        "iss": issuer,
        "aud": "rag-service",
        "sub": "u",
        "exp": now - 60,  # expired 1 min ago
        "iat": now - 3600,
    }
    token = _make_signed_jwt(claims)
    with pytest.raises(OidcInvalidToken, match="expired"):
        await svc.verify_id_token(token, config=cfg)


@pytest.mark.asyncio
async def test_verify_id_token_rejects_wrong_issuer() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc, cfg = _make_service(issuer)
    now = int(time.time())
    claims = {
        "iss": "https://attacker.com/realms/evil",
        "aud": "rag-service",
        "sub": "u",
        "exp": now + 300,
        "iat": now,
    }
    token = _make_signed_jwt(claims)
    with pytest.raises(OidcInvalidToken):
        await svc.verify_id_token(token, config=cfg)


@pytest.mark.asyncio
async def test_verify_id_token_rejects_wrong_audience() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc, cfg = _make_service(issuer)
    now = int(time.time())
    claims = {
        "iss": issuer,
        "aud": "other-service",
        "sub": "u",
        "exp": now + 300,
        "iat": now,
    }
    token = _make_signed_jwt(claims)
    with pytest.raises(OidcInvalidToken):
        await svc.verify_id_token(token, config=cfg)


@pytest.mark.asyncio
async def test_verify_id_token_unknown_kid_refreshes_jwks_after_key_rotation() -> None:
    """Rotation des clés côté IdP : un jeton signé par une clé au `kid` encore
    absent du trousseau en cache doit déclencher UN rechargement du JWKS —
    sans quoi tout login échoue jusqu'au redémarrage."""
    issuer = "https://kc.example.com/realms/test"
    rotated = RSAKey.generate_key(key_size=2048, private=True)
    served = [_jwks_payload()]

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "well-known" in url:
            return httpx.Response(200, json=_discovery_payload(issuer))
        if "jwks" in url:
            return httpx.Response(200, json=served[0])
        return httpx.Response(404)

    svc = OidcService(
        config_pool=None,
        public_url="https://rag.example.com",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    cfg = OidcConfig(issuer=issuer, client_id="rag-service")
    now = int(time.time())
    claims = {"iss": issuer, "aud": "rag-service", "sub": "u", "exp": now + 300, "iat": now}
    await svc.verify_id_token(_make_signed_jwt(claims), config=cfg)  # trousseau en cache

    pub = rotated.as_dict(private=False) | {"kid": "rotated-kid", "alg": "RS256", "use": "sig"}
    served[0] = {"keys": [pub]}
    token = jwt.encode({"alg": "RS256", "kid": "rotated-kid", "typ": "JWT"}, claims, rotated)
    decoded = await svc.verify_id_token(token, config=cfg)
    assert decoded["sub"] == "u"


@pytest.mark.asyncio
async def test_verify_access_token_checks_resource_audience_not_ui_client() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc, cfg = _make_service(issuer)
    now = int(time.time())
    base = {"iss": issuer, "sub": "u", "exp": now + 300, "iat": now}
    resource = "https://rag.example.com/mcp"
    ok = await svc.verify_access_token(
        _make_signed_jwt(base | {"aud": [resource, "account"]}), config=cfg, audience=resource
    )
    assert ok["sub"] == "u"
    # Jeton du client de l'IHM, ou d'un autre serveur MCP de la stack : refusé.
    for other in ("rag-service", "https://devpod.example.com/mcp"):
        with pytest.raises(OidcInvalidToken, match="invalid_claim:aud"):
            await svc.verify_access_token(
                _make_signed_jwt(base | {"aud": other}), config=cfg, audience=resource
            )
