from __future__ import annotations

import os
import time
from pathlib import Path

import bcrypt
from fastapi.testclient import TestClient

from rag.main import build_app

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _make_client_logged_local(pg_container: str, ttl_seconds: int = 28800) -> TestClient:
    """Même setup que test_auth_local._make_client mais auto-connecté via POST /auth/local/login.

    Retourne un TestClient déjà authentifié avec une session locale.
    """
    plain = "test-pwd-local"
    hash_ = bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=4)).decode()
    os.environ["DATABASE_URL"] = pg_container
    os.environ["RAG_POSTGRES_ADMIN_URL"] = pg_container.rsplit("/", 1)[0] + "/postgres"
    os.environ["RAG_MASTER_KEY"] = "mk_test_e2e_padding_padding_padding_padding"
    os.environ.setdefault("RAG_PUBLIC_URL", "http://localhost:8000")
    os.environ.pop("HARPOCRATE_API_TOKEN_RAG", None)
    os.environ.pop("HARPOCRATE_API_URL_RAG", None)
    os.environ.setdefault("HARPOCRATE_DEK", "passphrase-of-at-least-32-characters-long")
    os.environ.setdefault("RAG_API_KEY_DEK", "test-api-key-dek-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    os.environ.setdefault("ENVIRONMENT", "dev")
    os.environ["RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH"] = hash_
    os.environ["RAG_BOOTSTRAP_ADMIN_USERNAME"] = "admin"
    os.environ["RAG_BOOTSTRAP_SESSION_TTL_SECONDS"] = str(ttl_seconds)
    app = build_app(version="0.2.0", git_sha="testsha", migrations_dir=_MIGRATIONS_DIR)
    client = TestClient(app)
    resp = client.post("/auth/local/login", json={"username": "admin", "password": plain})
    assert resp.status_code == 200, f"login failed: {resp.json()}"
    return client


def _make_client_no_session(pg_container: str) -> TestClient:
    """Aucun hash bootstrap, pas de login → pas de session."""
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
    return TestClient(build_app(version="0.2.0", git_sha="testsha", migrations_dir=_MIGRATIONS_DIR))


def test_me_with_local_session_returns_local_user(pg_container: str) -> None:
    client = _make_client_logged_local(pg_container)
    resp = client.get("/me")
    assert resp.status_code == 200
    assert resp.json() == {"sub": "admin", "email": None, "name": None, "roles": ["rag-admin"]}


def test_me_with_expired_local_session_returns_401(pg_container: str) -> None:
    """TTL=1s → attendre → /me doit effacer le cookie et retourner local_session_expired."""
    client = _make_client_logged_local(pg_container, ttl_seconds=1)
    time.sleep(1.5)
    resp = client.get("/me")
    assert resp.status_code == 401
    assert resp.json()["error"] == "local_session_expired"


def test_me_with_no_session_returns_oidc_session_missing(pg_container: str) -> None:
    client = _make_client_no_session(pg_container)
    resp = client.get("/me")
    assert resp.status_code == 401
    assert resp.json()["error"] == "oidc_session_missing"
