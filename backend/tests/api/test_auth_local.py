from __future__ import annotations

import os

import bcrypt
import pytest
from fastapi.testclient import TestClient

from rag.main import build_app

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

_MIGRATIONS_DIR = __import__("pathlib").Path(__file__).resolve().parents[2] / "migrations"


@pytest.fixture
def bootstrap_hash() -> str:
    return _make_hash()


@pytest.fixture
def client_with_bootstrap(pg_container: str, bootstrap_hash: str) -> TestClient:
    """TestClient avec bootstrap activé (hash valide posé dans l'env)."""
    os.environ["DATABASE_URL"] = pg_container
    os.environ["RAG_POSTGRES_ADMIN_URL"] = pg_container.rsplit("/", 1)[0] + "/postgres"
    os.environ["RAG_MASTER_KEY"] = "mk_test_e2e_padding_padding_padding_padding"
    os.environ.setdefault("RAG_PUBLIC_URL", "http://localhost:8000")
    os.environ.pop("HARPOCRATE_API_TOKEN_RAG", None)
    os.environ.pop("HARPOCRATE_API_URL_RAG", None)
    os.environ.setdefault("HARPOCRATE_DEK", "passphrase-of-at-least-32-characters-long")
    os.environ.setdefault("RAG_API_KEY_DEK", "test-api-key-dek-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    os.environ.setdefault("ENVIRONMENT", "dev")
    os.environ["RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH"] = bootstrap_hash
    os.environ["RAG_BOOTSTRAP_ADMIN_USERNAME"] = _USERNAME

    app = build_app(version="0.2.0", git_sha="testsha", migrations_dir=_MIGRATIONS_DIR)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_without_bootstrap(pg_container: str) -> TestClient:
    """TestClient avec bootstrap désactivé (hash vide)."""
    os.environ["DATABASE_URL"] = pg_container
    os.environ["RAG_POSTGRES_ADMIN_URL"] = pg_container.rsplit("/", 1)[0] + "/postgres"
    os.environ["RAG_MASTER_KEY"] = "mk_test_e2e_padding_padding_padding_padding"
    os.environ.setdefault("RAG_PUBLIC_URL", "http://localhost:8000")
    os.environ.pop("HARPOCRATE_API_TOKEN_RAG", None)
    os.environ.pop("HARPOCRATE_API_URL_RAG", None)
    os.environ.setdefault("HARPOCRATE_DEK", "passphrase-of-at-least-32-characters-long")
    os.environ.setdefault("RAG_API_KEY_DEK", "test-api-key-dek-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    os.environ.setdefault("ENVIRONMENT", "dev")
    os.environ["RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH"] = ""
    os.environ["RAG_BOOTSTRAP_ADMIN_USERNAME"] = _USERNAME

    app = build_app(version="0.2.0", git_sha="testsha", migrations_dir=_MIGRATIONS_DIR)
    with TestClient(app) as c:
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
    assert "session" in resp.cookies or client_with_bootstrap.cookies.get("session") is not None


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
