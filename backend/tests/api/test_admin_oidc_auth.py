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
    return jwt.encode({"alg": "RS256", "kid": _KID, "typ": "JWT"}, claims, _RSA_KEY)


def _jwks() -> dict[str, Any]:
    pub = _RSA_KEY.as_dict(private=False)
    pub["kid"] = _KID
    pub["alg"] = "RS256"
    pub["use"] = "sig"
    return {"keys": [pub]}


def _discovery() -> dict[str, Any]:
    return {
        "issuer": _ISSUER,
        "authorization_endpoint": f"{_ISSUER}/auth",
        "token_endpoint": f"{_ISSUER}/token",
        "end_session_endpoint": f"{_ISSUER}/logout",
        "jwks_uri": f"{_ISSUER}/jwks",
    }


def _install_keycloak_mock(client: TestClient, *, roles: list[str]) -> None:
    """Setup OIDC mock : remplace le http_client de OidcService.

    Le token_endpoint lit le nonce depuis `app.state._kc_mock_state["last_nonce"]`
    pour valider le claim — même pattern que test_auth_flow.py.
    """
    state: dict[str, str] = {"last_nonce": ""}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "well-known" in url:
            return httpx.Response(200, json=_discovery())
        if "/jwks" in url:
            return httpx.Response(200, json=_jwks())
        if url.endswith("/token"):
            now = int(time.time())
            claims = {
                "iss": _ISSUER,
                "aud": _CLIENT_ID,
                "sub": "u",
                "email": "test@example.com",
                "name": "Test",
                "exp": now + 300,
                "iat": now,
                "nonce": state["last_nonce"],
                "resource_access": {_CLIENT_ID: {"roles": roles}},
            }
            return httpx.Response(
                200,
                json={
                    "id_token": _signed(claims),
                    "access_token": "at",
                    "refresh_token": "rt",
                    "expires_in": 300,
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client.app.state.oidc._http_client = httpx.AsyncClient(  # type: ignore[attr-defined]
        transport=transport
    )
    client.app.state._kc_mock_state = state  # type: ignore[attr-defined]
    client.app.state.oidc._discovery_cache.clear()  # type: ignore[attr-defined]
    client.app.state.oidc._jwks_cache.clear()  # type: ignore[attr-defined]


def _seed_and_login(
    client: TestClient,
    admin_headers: dict[str, str],
    *,
    roles: list[str],
) -> None:
    """Pose la config OIDC + simule un login complet pour avoir un cookie session."""
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
    client.app.state.resolver.known.add("kc_test_secret")  # type: ignore[attr-defined]

    _install_keycloak_mock(client, roles=roles)

    login_r = client.get("/auth/login", follow_redirects=False)
    params = parse_qs(urlparse(login_r.headers["location"]).query)
    nonce = params["nonce"][0]
    state = params["state"][0]

    # Injecte le nonce pour que le mock token_endpoint le retourne dans le claim.
    client.app.state._kc_mock_state["last_nonce"] = nonce  # type: ignore[attr-defined]

    cb = client.get(
        f"/auth/callback?code=x&state={state}",
        follow_redirects=False,
    )
    assert cb.status_code == 302, cb.text


def test_post_workspaces_with_master_key_still_works(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    """Non-régression : Bearer master-key reste accepté."""
    r = admin_client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={
            "name": "ws_mk",
            "api_key_vault": "rag",
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 201


def test_post_workspaces_with_oidc_admin_role_succeeds(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    """OIDC rag-admin sans Bearer → 201."""
    _seed_and_login(admin_client, admin_headers, roles=["rag-admin"])

    r = admin_client.post(
        "/api/admin/workspaces",
        json={
            "name": "ws_oidc",
            "api_key_vault": "rag",
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 201, r.text


def test_post_workspaces_with_oidc_viewer_role_returns_403(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    """OIDC rag-viewer sans Bearer → 403 oidc_role_forbidden."""
    _seed_and_login(admin_client, admin_headers, roles=["rag-viewer"])

    r = admin_client.post(
        "/api/admin/workspaces",
        json={
            "name": "ws_viewer",
            "api_key_vault": "rag",
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 403
    assert r.json()["error"] == "oidc_role_forbidden"


def test_post_workspaces_without_auth_returns_401(
    admin_client: TestClient,
    cleanup_ws_dbs_api: None,
) -> None:
    """Sans Bearer ni cookie → 401."""
    r = admin_client.post(
        "/api/admin/workspaces",
        json={"name": "x", "api_key_vault": "rag", "indexer": {"provider": "x", "model": "x"}},
    )
    assert r.status_code == 401


def test_admin_oidc_endpoint_accepts_oidc_admin_role(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    """`POST /admin/oidc` accepte OIDC rag-admin sans Bearer."""
    _seed_and_login(admin_client, admin_headers, roles=["rag-admin"])

    # Appel sans Bearer (cookie OIDC actif avec rôle rag-admin)
    r = admin_client.post(
        "/api/admin/oidc",
        json={
            "issuer": "https://kc.other.com/realms/r",
            "client_id": "other",
            "client_secret_ref": "other_ref",
        },
    )
    assert r.status_code in (200, 201), r.text


def test_post_oidc_with_oidc_viewer_role_returns_403(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    """OIDC rag-viewer sans Bearer → 403 oidc_role_forbidden sur POST /admin/oidc."""
    _seed_and_login(admin_client, admin_headers, roles=["rag-viewer"])

    r = admin_client.post(
        "/api/admin/oidc",
        json={
            "issuer": "https://kc.example.com/realms/test",
            "client_id": "rag",
            "client_secret_ref": "kc_rag_secret",
        },
    )
    assert r.status_code == 403
    assert r.json()["error"] == "oidc_role_forbidden"
