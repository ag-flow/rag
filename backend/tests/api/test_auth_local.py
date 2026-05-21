from __future__ import annotations

import bcrypt
import pytest
from fastapi.testclient import TestClient

from tests.api._helpers import make_app_client

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

_USERNAME = "admin"
_PASSWORD = "secret-password-for-tests"


def _make_hash(password: str = _PASSWORD) -> str:
    """Hash bcrypt rapide (rounds=4) pour les tests."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=4)).decode("utf-8")


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def bootstrap_hash() -> str:
    return _make_hash()


@pytest.fixture
def client_with_bootstrap(pg_container: str, bootstrap_hash: str) -> TestClient:
    """TestClient avec bootstrap activé (hash valide posé dans l'env)."""
    with make_app_client(pg_container, password_hash=bootstrap_hash) as c:
        yield c


@pytest.fixture
def client_without_bootstrap(pg_container: str) -> TestClient:
    """TestClient avec bootstrap désactivé (hash vide)."""
    with make_app_client(pg_container, password_hash="") as c:
        yield c


# ──────────────────────────────────────────────
# Tests login
# ──────────────────────────────────────────────


def test_local_login_correct_credentials_returns_200(
    client_with_bootstrap: TestClient,
) -> None:
    resp = client_with_bootstrap.post(
        "/auth/local/login",
        json={"username": _USERNAME, "password": _PASSWORD},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    # Cookie de session posé
    assert "session" in resp.cookies


def test_local_login_wrong_password_returns_401(
    client_with_bootstrap: TestClient,
) -> None:
    resp = client_with_bootstrap.post(
        "/auth/local/login",
        json={"username": _USERNAME, "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid_credentials"


def test_local_login_wrong_username_returns_401(
    client_with_bootstrap: TestClient,
) -> None:
    resp = client_with_bootstrap.post(
        "/auth/local/login",
        json={"username": "unknown-user", "password": _PASSWORD},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid_credentials"


def test_local_login_bootstrap_disabled_returns_503(
    client_without_bootstrap: TestClient,
) -> None:
    resp = client_without_bootstrap.post(
        "/auth/local/login",
        json={"username": _USERNAME, "password": _PASSWORD},
    )
    assert resp.status_code == 503
    assert resp.json()["error"] == "bootstrap_disabled"


def test_local_login_invalid_body_returns_422(
    client_with_bootstrap: TestClient,
) -> None:
    resp = client_with_bootstrap.post(
        "/auth/local/login",
        json={"username": _USERNAME},  # password manquant
    )
    assert resp.status_code == 422


# ──────────────────────────────────────────────
# Tests logout
# ──────────────────────────────────────────────


def test_local_logout_without_session_returns_204(
    client_with_bootstrap: TestClient,
) -> None:
    resp = client_with_bootstrap.post("/auth/local/logout")
    assert resp.status_code == 204


def test_local_login_then_logout_clears_session(
    client_with_bootstrap: TestClient,
) -> None:
    # Login
    login_resp = client_with_bootstrap.post(
        "/auth/local/login",
        json={"username": _USERNAME, "password": _PASSWORD},
    )
    assert login_resp.status_code == 200

    # Logout
    logout_resp = client_with_bootstrap.post("/auth/local/logout")
    assert logout_resp.status_code == 204

    # /me doit retourner 401 (pas de session valide)
    me_resp = client_with_bootstrap.get("/me")
    assert me_resp.status_code == 401


# ──────────────────────────────────────────────
# Tests /api/auth/methods
# ──────────────────────────────────────────────


def test_get_auth_methods_bootstrap_enabled_returns_correct_payload(
    client_with_bootstrap: TestClient,
) -> None:
    resp = client_with_bootstrap.get("/api/auth/methods")
    assert resp.status_code == 200
    body = resp.json()
    assert body["bootstrap_enabled"] is True
    assert body["oidc_configured"] is False


def test_get_auth_methods_bootstrap_disabled_returns_correct_payload(
    client_without_bootstrap: TestClient,
) -> None:
    resp = client_without_bootstrap.get("/api/auth/methods")
    assert resp.status_code == 200
    body = resp.json()
    assert body["bootstrap_enabled"] is False
    assert body["oidc_configured"] is False
