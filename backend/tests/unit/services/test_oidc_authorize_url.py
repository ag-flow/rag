from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from rag.services.oidc import OidcService


def _discovery_payload(issuer: str) -> dict:
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/protocol/openid-connect/auth",
        "token_endpoint": f"{issuer}/protocol/openid-connect/token",
        "end_session_endpoint": f"{issuer}/protocol/openid-connect/logout",
        "jwks_uri": f"{issuer}/protocol/openid-connect/certs",
    }


def _make_service_with_config(issuer: str) -> OidcService:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_discovery_payload(issuer))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "issuer": issuer,
            "client_id": "rag-service",
            "client_secret_ref": "kc_secret",
        }
    )
    svc = OidcService(
        config_pool=pool,
        secret_resolver=None,
        public_url="https://rag.example.com",
        http_client=client,
    )
    return svc


@pytest.mark.asyncio
async def test_build_authorize_url_includes_required_params() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc = _make_service_with_config(issuer)
    url, state, nonce = await svc.build_authorize_url()
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.netloc == "kc.example.com"
    assert parsed.path == "/realms/test/protocol/openid-connect/auth"
    assert params["client_id"] == ["rag-service"]
    assert params["redirect_uri"] == ["https://rag.example.com/auth/callback"]
    assert params["response_type"] == ["code"]
    assert "openid" in params["scope"][0]
    assert params["state"] == [state]
    assert params["nonce"] == [nonce]
    # state et nonce sont des strings aléatoires non vides
    assert len(state) >= 16
    assert len(nonce) >= 16


@pytest.mark.asyncio
async def test_build_authorize_url_state_and_nonce_unique() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc = _make_service_with_config(issuer)
    _, s1, n1 = await svc.build_authorize_url()
    _, s2, n2 = await svc.build_authorize_url()
    assert s1 != s2
    assert n1 != n2


@pytest.mark.asyncio
async def test_build_logout_url_includes_id_token_hint_and_redirect() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc = _make_service_with_config(issuer)
    cfg = await svc.get_config()
    assert cfg is not None
    url = await svc.build_logout_url(id_token="dummy.jwt.value", config=cfg)
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    assert parsed.path == "/realms/test/protocol/openid-connect/logout"
    assert params["id_token_hint"] == ["dummy.jwt.value"]
    assert params["post_logout_redirect_uri"] == ["https://rag.example.com/"]
