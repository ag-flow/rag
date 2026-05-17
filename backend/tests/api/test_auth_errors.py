from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient


def test_auth_login_503_when_oidc_not_configured(
    admin_client: TestClient,
) -> None:
    r = admin_client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 503
    assert r.json()["error"] == "oidc_not_configured"


def test_auth_callback_400_state_missing(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    admin_client.post(
        "/api/admin/oidc",
        headers=admin_headers,
        json={
            "issuer": "https://kc.example.com/realms/test",
            "client_id": "rag-service",
            "client_secret_ref": "kc_secret",
        },
    )
    # Pas de cookie state préalable → state_missing
    r = admin_client.get("/auth/callback?code=x&state=fake", follow_redirects=False)
    assert r.status_code == 400
    assert r.json()["error"] == "oidc_state_missing"


def test_me_401_without_session(admin_client: TestClient) -> None:
    r = admin_client.get("/me")
    assert r.status_code == 401
    assert r.json()["error"] == "oidc_session_missing"


def test_refresh_401_without_session(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    admin_client.post(
        "/api/admin/oidc",
        headers=admin_headers,
        json={
            "issuer": "https://kc.example.com/realms/test",
            "client_id": "rag-service",
            "client_secret_ref": "kc_secret",
        },
    )
    r = admin_client.post("/auth/refresh")
    assert r.status_code == 401
    assert r.json()["error"] == "oidc_session_missing"


def test_auth_callback_503_when_oidc_not_configured(
    admin_client: TestClient,
) -> None:
    """Callback sans config OIDC → 503 (branche OidcNotConfigured ligne 58)."""
    # Pas de config OIDC du tout — déclenche OidcNotConfigured dans callback
    r = admin_client.get("/auth/callback?code=x&state=y", follow_redirects=False)
    assert r.status_code == 503
    assert r.json()["error"] == "oidc_not_configured"


def test_auth_callback_400_state_mismatch(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    """State du cookie != state QS → 400 oidc_state_mismatch (ligne 64)."""
    admin_client.post(
        "/api/admin/oidc",
        headers=admin_headers,
        json={
            "issuer": "https://kc.example.com/realms/test",
            "client_id": "rag-service",
            "client_secret_ref": "kc_secret",
        },
    )
    # On provoque d'abord un /auth/login pour que la session contienne un state valide
    # (sans mock du discovery — le login échoue, mais la session est créée avant)
    # Alternative : on injecte directement le state cookie via starlette session.
    # Mais avec TestClient + SessionMiddleware on peut forcer via /auth/login.
    # /auth/login essaie de faire discovery (échoue si pas de mock), donc on utilise
    # un approach différent : on seed la session via /auth/login avec un mock minimal.
    # Pour rester simple : on lit le state du redirect et on envoie un mauvais state.
    # Le test existant test_auth_callback_400_state_missing couvre déjà le cas sans session.
    # Ici on teste state présent mais ne correspond pas.
    #
    # On set manuellement la session via un endpoint de test n'existant pas.
    # On ne peut pas. On va utiliser l'approach: login avec discovery mock minimal.
    # On injecte un mock httpx qui accepte juste le discovery.
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "well-known" in url:
            return httpx.Response(
                200,
                json={
                    "issuer": "https://kc.example.com/realms/test",
                    "authorization_endpoint": "https://kc.example.com/realms/test/protocol/openid-connect/auth",
                    "token_endpoint": "https://kc.example.com/realms/test/protocol/openid-connect/token",
                    "end_session_endpoint": "https://kc.example.com/realms/test/protocol/openid-connect/logout",
                    "jwks_uri": "https://kc.example.com/realms/test/protocol/openid-connect/certs",
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    new_http = httpx.AsyncClient(transport=transport)
    admin_client.app.state.oidc._http_client = new_http  # type: ignore[attr-defined]
    admin_client.app.state.oidc._discovery_cache.clear()  # type: ignore[attr-defined]
    admin_client.app.state.resolver.known.add("kc_secret")  # type: ignore[attr-defined]

    # Login → obtient un redirect avec le bon state et stocke la session
    login_r = admin_client.get("/auth/login", follow_redirects=False)
    assert login_r.status_code == 302
    params = parse_qs(urlparse(login_r.headers["location"]).query)
    _good_state = params["state"][0]

    # Callback avec un state différent → 400 oidc_state_mismatch
    cb_r = admin_client.get(
        "/auth/callback?code=x&state=WRONG_STATE",
        follow_redirects=False,
    )
    assert cb_r.status_code == 400
    assert cb_r.json()["error"] == "oidc_state_mismatch"


def test_refresh_503_when_oidc_not_configured(admin_client: TestClient) -> None:
    """POST /auth/refresh sans config OIDC → 503 (ligne 88).

    Le refresh vérifie d'abord get_config() (avant la session), donc même
    sans session, si OIDC n'est pas configuré on obtient 503.
    """
    r = admin_client.post("/auth/refresh")
    assert r.status_code == 503
    assert r.json()["error"] == "oidc_not_configured"


def test_logout_without_config_redirects_to_public_url(
    admin_client: TestClient,
) -> None:
    """POST /auth/logout sans config OIDC → redirect vers public_url (ligne 124)."""
    r = admin_client.post("/auth/logout", follow_redirects=False)
    assert r.status_code == 302
    # Sans config OIDC, redirige vers public_url + /
    location = r.headers["location"]
    assert location.endswith("/")


def test_login_safe_next_rejects_double_slash(admin_client: TestClient) -> None:
    """_safe_next doit rejeter les paths débutant par '//' (anti open-redirect, ligne 25)."""
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "well-known" in url:
            return httpx.Response(
                200,
                json={
                    "issuer": "https://kc.example.com/realms/test",
                    "authorization_endpoint": "https://kc.example.com/realms/test/protocol/openid-connect/auth",
                    "token_endpoint": "https://kc.example.com/realms/test/protocol/openid-connect/token",
                    "end_session_endpoint": "https://kc.example.com/realms/test/protocol/openid-connect/logout",
                    "jwks_uri": "https://kc.example.com/realms/test/protocol/openid-connect/certs",
                },
            )
        return httpx.Response(404)

    admin_client.app.state.oidc._http_client = httpx.AsyncClient(  # type: ignore[attr-defined]
        transport=httpx.MockTransport(handler)
    )
    admin_client.app.state.oidc._discovery_cache.clear()  # type: ignore[attr-defined]

    # POST config oidc
    admin_client.app.state.oidc._http_client = httpx.AsyncClient(  # type: ignore[attr-defined]
        transport=httpx.MockTransport(handler)
    )
    # On doit avoir une config OIDC en base — re-use l'approche POST admin/oidc.
    # Ce test utilise admin_client propre par fixture donc pas de config → pas de login.
    # On passe directement au test de _safe_next en unité.
    from rag.api.auth import _safe_next

    assert _safe_next("//evil.com") == "/"
    assert _safe_next("//evil.com/path") == "/"
    assert _safe_next("/valid/path") == "/valid/path"
    assert _safe_next(None) == "/"
    assert _safe_next("") == "/"
    assert _safe_next("http://evil.com") == "/"
