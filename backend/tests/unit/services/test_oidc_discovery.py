from __future__ import annotations

import time

import httpx
import pytest
from joserfc.jwk import KeySet, RSAKey

from rag.api.errors import OidcKeycloakUnreachable
from rag.services.oidc import OidcConfig, OidcService


def _discovery_payload(issuer: str) -> dict:
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/protocol/openid-connect/auth",
        "token_endpoint": f"{issuer}/protocol/openid-connect/token",
        "end_session_endpoint": f"{issuer}/protocol/openid-connect/logout",
        "jwks_uri": f"{issuer}/protocol/openid-connect/certs",
    }


def _valid_jwks_payload() -> dict:
    """Génère un payload JWKS valide (vraie RSA key) pour que joserfc l'accepte."""
    key = RSAKey.generate_key(2048, parameters={"kid": "test-key"}, private=False)
    return KeySet([key]).as_dict()


@pytest.mark.asyncio
async def test_discover_fetches_well_known_and_caches() -> None:
    issuer = "https://kc.example.com/realms/test"
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=_discovery_payload(issuer))

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    svc = OidcService(
        config_pool=None,  # pas utilisé dans _discover
        secret_resolver=None,  # idem
        public_url="https://rag.example.com",
        http_client=client,
    )
    cfg = OidcConfig(
        issuer=issuer,
        client_id="rag-service",
        client_secret_ref="x",
    )
    d1 = await svc._discover(cfg)
    d2 = await svc._discover(cfg)
    assert d1.authorization_endpoint == f"{issuer}/protocol/openid-connect/auth"
    assert d1.token_endpoint == f"{issuer}/protocol/openid-connect/token"
    assert d1.end_session_endpoint == f"{issuer}/protocol/openid-connect/logout"
    assert d1.jwks_uri == f"{issuer}/protocol/openid-connect/certs"
    assert call_count == 1  # 2e appel utilise le cache
    assert d2 is d1  # même objet retourné depuis le cache


@pytest.mark.asyncio
async def test_discover_reloads_after_ttl() -> None:
    issuer = "https://kc.example.com/realms/test"
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=_discovery_payload(issuer))

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    svc = OidcService(
        config_pool=None,
        secret_resolver=None,
        public_url="https://rag.example.com",
        http_client=client,
    )
    cfg = OidcConfig(issuer=issuer, client_id="x", client_secret_ref="x")
    await svc._discover(cfg)
    # Simule l'expiration : remplace l'entrée par une version avec fetched_at très ancien
    for key in list(svc._discovery_cache):
        d = svc._discovery_cache[key]
        svc._discovery_cache[key] = type(d)(
            authorization_endpoint=d.authorization_endpoint,
            token_endpoint=d.token_endpoint,
            end_session_endpoint=d.end_session_endpoint,
            jwks_uri=d.jwks_uri,
            fetched_at=time.monotonic() - 3700,
        )
    await svc._discover(cfg)
    assert call_count == 2  # reload après TTL


@pytest.mark.asyncio
async def test_discover_raises_keycloak_unreachable_on_timeout() -> None:
    issuer = "https://kc.example.com/realms/test"

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    svc = OidcService(
        config_pool=None,
        secret_resolver=None,
        public_url="https://rag.example.com",
        http_client=client,
    )
    cfg = OidcConfig(issuer=issuer, client_id="x", client_secret_ref="x")
    with pytest.raises(OidcKeycloakUnreachable) as exc:
        await svc._discover(cfg)
    assert exc.value.issuer == issuer


@pytest.mark.asyncio
async def test_discover_raises_keycloak_unreachable_on_500() -> None:
    issuer = "https://kc.example.com/realms/test"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    svc = OidcService(
        config_pool=None,
        secret_resolver=None,
        public_url="https://rag.example.com",
        http_client=client,
    )
    cfg = OidcConfig(issuer=issuer, client_id="x", client_secret_ref="x")
    with pytest.raises(OidcKeycloakUnreachable):
        await svc._discover(cfg)


@pytest.mark.asyncio
async def test_jwks_fetches_and_caches() -> None:
    issuer = "https://kc.example.com/realms/test"
    valid_jwks = _valid_jwks_payload()
    jwks_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal jwks_calls
        if "well-known" in str(request.url):
            return httpx.Response(200, json=_discovery_payload(issuer))
        jwks_calls += 1
        return httpx.Response(200, json=valid_jwks)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    svc = OidcService(
        config_pool=None,
        secret_resolver=None,
        public_url="https://rag.example.com",
        http_client=client,
    )
    cfg = OidcConfig(issuer=issuer, client_id="x", client_secret_ref="x")
    d = await svc._discover(cfg)
    ks1 = await svc._jwks(d)
    ks2 = await svc._jwks(d)  # cache
    assert jwks_calls == 1
    assert ks2 is ks1  # même objet depuis le cache
    assert len(ks1.keys) == 1
