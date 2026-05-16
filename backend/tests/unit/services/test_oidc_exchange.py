from __future__ import annotations

import time
from typing import Any

import httpx
import pytest
from joserfc import jwt
from joserfc.jwk import RSAKey

from rag.api.errors import OidcInvalidCode, OidcInvalidToken, OidcSessionExpired
from rag.services.oidc import OidcConfig, OidcService

_RSA_KEY = RSAKey.generate_key(key_size=2048, private=True)
_KID = "test-key"


def _signed(claims: dict[str, Any]) -> str:
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


class _FakeResolver:
    async def resolve_with_retry(self, _ref: str) -> str:
        return "resolved-client-secret"


def _make_service(
    issuer: str,
    *,
    token_response: dict | None = None,
    token_status: int = 200,
    token_error_payload: dict | None = None,
) -> tuple[OidcService, OidcConfig]:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "well-known" in url:
            return httpx.Response(200, json=_discovery_payload(issuer))
        if "jwks" in url:
            return httpx.Response(200, json=_jwks_payload())
        if url.endswith("/token"):
            if token_status != 200:
                return httpx.Response(token_status, json=token_error_payload or {})
            return httpx.Response(200, json=token_response or {})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    svc = OidcService(
        config_pool=None,
        secret_resolver=_FakeResolver(),
        public_url="https://rag.example.com",
        http_client=client,
    )
    cfg = OidcConfig(issuer=issuer, client_id="rag-service", client_secret_ref="kc_secret")
    return svc, cfg


@pytest.mark.asyncio
async def test_exchange_code_happy_path() -> None:
    issuer = "https://kc.example.com/realms/test"
    now = int(time.time())
    id_token = _signed(
        {
            "iss": issuer,
            "aud": "rag-service",
            "sub": "u",
            "exp": now + 300,
            "iat": now,
            "nonce": "expected-nonce",
        }
    )
    svc, cfg = _make_service(
        issuer,
        token_response={
            "id_token": id_token,
            "access_token": "at-xyz",
            "refresh_token": "rt-xyz",
            "expires_in": 300,
            "token_type": "Bearer",
        },
    )
    tokens = await svc.exchange_code(
        code="auth-code-xyz",
        expected_nonce="expected-nonce",
        config=cfg,
    )
    assert tokens.id_token == id_token
    assert tokens.access_token == "at-xyz"
    assert tokens.refresh_token == "rt-xyz"
    assert tokens.expires_at > now


@pytest.mark.asyncio
async def test_exchange_code_rejects_nonce_mismatch() -> None:
    issuer = "https://kc.example.com/realms/test"
    now = int(time.time())
    id_token = _signed(
        {
            "iss": issuer,
            "aud": "rag-service",
            "sub": "u",
            "exp": now + 300,
            "iat": now,
            "nonce": "actual-nonce",
        }
    )
    svc, cfg = _make_service(
        issuer,
        token_response={
            "id_token": id_token,
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 300,
        },
    )
    with pytest.raises(OidcInvalidToken, match="nonce"):
        await svc.exchange_code(
            code="x",
            expected_nonce="other-nonce",
            config=cfg,
        )


@pytest.mark.asyncio
async def test_exchange_code_rejects_400_keycloak_error() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc, cfg = _make_service(
        issuer,
        token_status=400,
        token_error_payload={"error": "invalid_grant"},
    )
    with pytest.raises(OidcInvalidCode) as exc:
        await svc.exchange_code(code="x", expected_nonce="n", config=cfg)
    assert exc.value.reason == "invalid_grant"


@pytest.mark.asyncio
async def test_refresh_happy_path() -> None:
    issuer = "https://kc.example.com/realms/test"
    now = int(time.time())
    new_id_token = _signed(
        {
            "iss": issuer,
            "aud": "rag-service",
            "sub": "u",
            "exp": now + 300,
            "iat": now,
        }
    )
    svc, cfg = _make_service(
        issuer,
        token_response={
            "id_token": new_id_token,
            "access_token": "new-at",
            "refresh_token": "new-rt",
            "expires_in": 300,
        },
    )
    tokens = await svc.refresh(refresh_token="old-rt", config=cfg)
    assert tokens.id_token == new_id_token
    assert tokens.refresh_token == "new-rt"


@pytest.mark.asyncio
async def test_refresh_rejected_raises_session_expired() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc, cfg = _make_service(
        issuer,
        token_status=400,
        token_error_payload={"error": "invalid_grant"},
    )
    with pytest.raises(OidcSessionExpired):
        await svc.refresh(refresh_token="stale-rt", config=cfg)
