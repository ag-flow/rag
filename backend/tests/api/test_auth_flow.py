from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import RSAKey

_RSA_KEY = RSAKey.generate_key(key_size=2048, private=True)
_KID = "test-kid"
_ISSUER = "https://kc.example.com/realms/test"
_CLIENT_ID = "rag-service"


def _signed(claims: dict[str, Any]) -> str:
    header = {"alg": "RS256", "kid": _KID, "typ": "JWT"}
    return jwt.encode(header, claims, _RSA_KEY)


def _jwks_payload() -> dict[str, Any]:
    pub = _RSA_KEY.as_dict(private=False)
    pub["kid"] = _KID
    pub["alg"] = "RS256"
    pub["use"] = "sig"
    return {"keys": [pub]}


def _discovery_payload() -> dict[str, Any]:
    return {
        "issuer": _ISSUER,
        "authorization_endpoint": f"{_ISSUER}/protocol/openid-connect/auth",
        "token_endpoint": f"{_ISSUER}/protocol/openid-connect/token",
        "end_session_endpoint": f"{_ISSUER}/protocol/openid-connect/logout",
        "jwks_uri": f"{_ISSUER}/protocol/openid-connect/certs",
    }


def _install_keycloak_mock(client: TestClient, *, roles: list[str] | None = None) -> None:
    """Replace OidcService's http_client with a MockTransport simulating Keycloak.

    The token_endpoint reads the nonce from app.state._kc_mock_state["last_nonce"]
    so the test can inject it after `/auth/login` (which generates it)."""
    state: dict[str, str] = {"last_nonce": ""}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "well-known" in url:
            return httpx.Response(200, json=_discovery_payload())
        if "/certs" in url:
            return httpx.Response(200, json=_jwks_payload())
        if url.endswith("/token"):
            now = int(time.time())
            claims = {
                "iss": _ISSUER,
                "aud": _CLIENT_ID,
                "sub": "user-uuid-42",
                "email": "test@example.com",
                "name": "Test User",
                "exp": now + 300,
                "iat": now,
                "nonce": state["last_nonce"],
                "resource_access": {
                    _CLIENT_ID: {"roles": roles or ["rag-viewer"]},
                },
            }
            return httpx.Response(
                200,
                json={
                    "id_token": _signed(claims),
                    "access_token": "at-test",
                    "refresh_token": "rt-test",
                    "expires_in": 300,
                    "token_type": "Bearer",
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    new_client = httpx.AsyncClient(transport=transport)
    client.app.state.oidc._http_client = new_client  # type: ignore[attr-defined]
    client.app.state._kc_mock_state = state  # type: ignore[attr-defined]
    # Reset caches discovery/JWKS pour s'assurer qu'on utilise le nouveau client
    client.app.state.oidc._discovery_cache.clear()  # type: ignore[attr-defined]
    client.app.state.oidc._jwks_cache.clear()  # type: ignore[attr-defined]


def _seed_oidc_config(client: TestClient, admin_headers: dict[str, str]) -> None:
    r = client.post(
        "/api/admin/oidc",
        headers=admin_headers,
        json={
            "issuer": _ISSUER,
            "client_id": _CLIENT_ID,
            "client_secret_ref": "kc_test_secret",
        },
    )
    assert r.status_code == 201, r.text


def _stub_secret_resolver(client: TestClient) -> None:
    """Le stub resolver de conftest accepte déjà certaines refs ;
    on ajoute kc_test_secret."""
    client.app.state.resolver.known.add("kc_test_secret")  # type: ignore[attr-defined]


def test_auth_login_redirects_to_keycloak_with_state_and_nonce(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    _seed_oidc_config(admin_client, admin_headers)
    _install_keycloak_mock(admin_client)
    _stub_secret_resolver(admin_client)

    r = admin_client.get("/auth/login?next=/ui/workspaces", follow_redirects=False)
    assert r.status_code == 302, r.text
    location = r.headers["location"]
    parsed = urlparse(location)
    params = parse_qs(parsed.query)
    assert parsed.netloc == "kc.example.com"
    assert params["client_id"] == [_CLIENT_ID]
    assert "state" in params
    assert "nonce" in params


def test_auth_callback_sets_session_cookie_and_redirects_next(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    _seed_oidc_config(admin_client, admin_headers)
    _install_keycloak_mock(admin_client)
    _stub_secret_resolver(admin_client)

    # 1. /auth/login pour capturer state + nonce (et set state cookie)
    login_r = admin_client.get("/auth/login?next=/ui/x", follow_redirects=False)
    auth_url = login_r.headers["location"]
    params = parse_qs(urlparse(auth_url).query)
    state = params["state"][0]
    nonce = params["nonce"][0]
    # Le mock Keycloak va recevoir le code et retourner un id_token avec ce nonce
    admin_client.app.state._kc_mock_state["last_nonce"] = nonce  # type: ignore[attr-defined]

    # 2. /auth/callback?code=...&state=...
    cb_r = admin_client.get(
        f"/auth/callback?code=auth-code-xyz&state={state}",
        follow_redirects=False,
    )
    assert cb_r.status_code == 302, cb_r.text
    assert cb_r.headers["location"] == "/ui/x"


def test_me_returns_user_info_after_login(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    _seed_oidc_config(admin_client, admin_headers)
    _install_keycloak_mock(admin_client, roles=["rag-viewer"])
    _stub_secret_resolver(admin_client)

    login_r = admin_client.get("/auth/login", follow_redirects=False)
    params = parse_qs(urlparse(login_r.headers["location"]).query)
    admin_client.app.state._kc_mock_state["last_nonce"] = params["nonce"][0]  # type: ignore[attr-defined]

    cb_r = admin_client.get(
        f"/auth/callback?code=x&state={params['state'][0]}",
        follow_redirects=False,
    )
    assert cb_r.status_code == 302

    me_r = admin_client.get("/me")
    assert me_r.status_code == 200, me_r.text
    body = me_r.json()
    assert body["sub"] == "user-uuid-42"
    assert body["email"] == "test@example.com"
    assert body["roles"] == ["rag-viewer"]


def test_logout_clears_session_and_redirects_keycloak_logout(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    _seed_oidc_config(admin_client, admin_headers)
    _install_keycloak_mock(admin_client)
    _stub_secret_resolver(admin_client)

    # Login d'abord
    login_r = admin_client.get("/auth/login", follow_redirects=False)
    params = parse_qs(urlparse(login_r.headers["location"]).query)
    admin_client.app.state._kc_mock_state["last_nonce"] = params["nonce"][0]  # type: ignore[attr-defined]
    admin_client.get(
        f"/auth/callback?code=x&state={params['state'][0]}",
        follow_redirects=False,
    )

    # Logout
    out_r = admin_client.post("/auth/logout", follow_redirects=False)
    assert out_r.status_code == 302
    assert "logout" in out_r.headers["location"]
    assert "id_token_hint" in out_r.headers["location"]

    # /me ne doit plus marcher
    me_r = admin_client.get("/me")
    assert me_r.status_code == 401


def test_refresh_returns_ok_with_new_tokens(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    """POST /auth/refresh avec session active → 200 {"ok": true} (lignes 94-108)."""
    _seed_oidc_config(admin_client, admin_headers)
    _install_keycloak_mock(admin_client)
    _stub_secret_resolver(admin_client)

    # Login complet
    login_r = admin_client.get("/auth/login", follow_redirects=False)
    params = parse_qs(urlparse(login_r.headers["location"]).query)
    admin_client.app.state._kc_mock_state["last_nonce"] = params["nonce"][0]  # type: ignore[attr-defined]
    cb_r = admin_client.get(
        f"/auth/callback?code=x&state={params['state'][0]}",
        follow_redirects=False,
    )
    assert cb_r.status_code == 302

    # Refresh — le mock token_endpoint retourne un nouveau id_token
    import httpx

    def refresh_handler(request: httpx.Request) -> httpx.Response:
        import time

        url = str(request.url)
        if "well-known" in url:
            return httpx.Response(200, json=_discovery_payload())
        if "/certs" in url:
            return httpx.Response(200, json=_jwks_payload())
        if url.endswith("/token"):
            now = int(time.time())
            claims = {
                "iss": _ISSUER,
                "aud": _CLIENT_ID,
                "sub": "user-uuid-42",
                "email": "test@example.com",
                "name": "Test User",
                "exp": now + 600,
                "iat": now,
                "nonce": "",
                "resource_access": {_CLIENT_ID: {"roles": ["rag-viewer"]}},
            }
            return httpx.Response(
                200,
                json={
                    "id_token": _signed(claims),
                    "access_token": "at-refreshed",
                    "refresh_token": "rt-refreshed",
                    "expires_in": 600,
                    "token_type": "Bearer",
                },
            )
        return httpx.Response(404)

    admin_client.app.state.oidc._http_client = httpx.AsyncClient(  # type: ignore[attr-defined]
        transport=httpx.MockTransport(refresh_handler)
    )
    admin_client.app.state.oidc._discovery_cache.clear()  # type: ignore[attr-defined]
    admin_client.app.state.oidc._jwks_cache.clear()  # type: ignore[attr-defined]

    refresh_r = admin_client.post("/auth/refresh")
    assert refresh_r.status_code == 200, refresh_r.text
    assert refresh_r.json() == {"ok": True}


def test_refresh_401_when_refresh_token_expired(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    """POST /auth/refresh quand le refresh_token est expiré (côté IDP) → 401 session_expired.

    Couvre les lignes 99-101 de auth.py : OidcSessionExpired catchée dans le try/except
    qui purge la session et re-raise.
    """
    _seed_oidc_config(admin_client, admin_headers)
    _install_keycloak_mock(admin_client)
    _stub_secret_resolver(admin_client)

    # Login pour avoir une session valide
    login_r = admin_client.get("/auth/login", follow_redirects=False)
    params = parse_qs(urlparse(login_r.headers["location"]).query)
    admin_client.app.state._kc_mock_state["last_nonce"] = params["nonce"][0]  # type: ignore[attr-defined]
    cb_r = admin_client.get(
        f"/auth/callback?code=x&state={params['state'][0]}",
        follow_redirects=False,
    )
    assert cb_r.status_code == 302

    # Remplace le mock httpx pour que le token_endpoint retourne 400 invalid_grant
    import httpx

    def expired_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "well-known" in url:
            return httpx.Response(200, json=_discovery_payload())
        if "/certs" in url:
            return httpx.Response(200, json=_jwks_payload())
        if url.endswith("/token"):
            return httpx.Response(
                400,
                json={"error": "invalid_grant", "error_description": "Refresh token expired"},
            )
        return httpx.Response(404)

    admin_client.app.state.oidc._http_client = httpx.AsyncClient(  # type: ignore[attr-defined]
        transport=httpx.MockTransport(expired_handler)
    )
    admin_client.app.state.oidc._discovery_cache.clear()  # type: ignore[attr-defined]
    admin_client.app.state.oidc._jwks_cache.clear()  # type: ignore[attr-defined]

    refresh_r = admin_client.post("/auth/refresh")
    assert refresh_r.status_code == 401, refresh_r.text
    assert refresh_r.json()["error"] == "oidc_session_expired"

    # Session doit être purgée : /me retourne 401 session_missing
    me_r = admin_client.get("/me")
    assert me_r.status_code == 401
