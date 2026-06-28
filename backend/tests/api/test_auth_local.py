from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.api._helpers import make_app_client

_USERNAME = "admin"
_EMAIL = "admin@example.com"
_PASSWORD = "secret-password-for-tests"


@pytest.fixture
def client(pg_container: str) -> TestClient:
    with make_app_client(pg_container) as c:
        yield c


@pytest.fixture
def client_with_user(pg_container: str) -> TestClient:
    """TestClient avec un utilisateur déjà créé en base."""
    with make_app_client(pg_container) as c:
        c.post(
            "/api/setup/init-admin",
            json={"username": _USERNAME, "email": _EMAIL, "password": _PASSWORD},
        )
        yield c


# ──────────────────────────────────────────────
# Tests login
# ──────────────────────────────────────────────


def test_local_login_correct_credentials_returns_200(
    client_with_user: TestClient,
) -> None:
    resp = client_with_user.post(
        "/auth/local/login",
        json={"username": _USERNAME, "password": _PASSWORD},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert "session" in resp.cookies


def test_local_login_wrong_password_returns_401(
    client_with_user: TestClient,
) -> None:
    resp = client_with_user.post(
        "/auth/local/login",
        json={"username": _USERNAME, "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid_credentials"


def test_local_login_wrong_username_returns_401(
    client_with_user: TestClient,
) -> None:
    resp = client_with_user.post(
        "/auth/local/login",
        json={"username": "unknown-user", "password": _PASSWORD},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid_credentials"


def test_local_login_no_user_returns_503(
    client: TestClient,
) -> None:
    resp = client.post(
        "/auth/local/login",
        json={"username": _USERNAME, "password": _PASSWORD},
    )
    assert resp.status_code == 503
    assert resp.json()["error"] == "setup_required"


def test_local_login_invalid_body_returns_422(
    client_with_user: TestClient,
) -> None:
    resp = client_with_user.post(
        "/auth/local/login",
        json={"username": _USERNAME},  # password manquant
    )
    assert resp.status_code == 422


# ──────────────────────────────────────────────
# Tests logout
# ──────────────────────────────────────────────


def test_local_logout_without_session_returns_204(
    client_with_user: TestClient,
) -> None:
    resp = client_with_user.post("/auth/local/logout")
    assert resp.status_code == 204


def test_local_login_then_logout_clears_session(
    client_with_user: TestClient,
) -> None:
    client_with_user.post(
        "/auth/local/login",
        json={"username": _USERNAME, "password": _PASSWORD},
    )
    client_with_user.post("/auth/local/logout")
    me_resp = client_with_user.get("/me")
    assert me_resp.status_code == 401


# ──────────────────────────────────────────────
# Tests /api/auth/methods
# ──────────────────────────────────────────────


def test_get_auth_methods_with_user_returns_local_enabled(
    client_with_user: TestClient,
) -> None:
    resp = client_with_user.get("/api/auth/methods")
    assert resp.status_code == 200
    body = resp.json()
    assert body["local_auth_enabled"] is True
    assert body["needs_setup"] is False
    assert body["oidc_configured"] is False


def test_get_auth_methods_no_user_returns_needs_setup(
    client: TestClient,
) -> None:
    resp = client.get("/api/auth/methods")
    assert resp.status_code == 200
    body = resp.json()
    assert body["local_auth_enabled"] is False
    assert body["needs_setup"] is True
    assert body["oidc_configured"] is False
