from __future__ import annotations

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
        "/admin/oidc",
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
        "/admin/oidc",
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
