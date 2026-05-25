from __future__ import annotations

import time

import bcrypt
from fastapi.testclient import TestClient

from tests.api._helpers import make_app_client


def _logged_local(pg_container: str, ttl_seconds: int = 28800) -> TestClient:
    """TestClient auto-connecté via POST /auth/local/login."""
    plain = "test-pwd-local"
    hash_ = bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=4)).decode()
    client = make_app_client(pg_container, password_hash=hash_, ttl_seconds=ttl_seconds)
    resp = client.post("/auth/local/login", json={"username": "admin", "password": plain})
    assert resp.status_code == 200, f"login failed: {resp.json()}"
    return client


def test_me_with_local_session_returns_local_user(pg_container: str) -> None:
    client = _logged_local(pg_container)
    resp = client.get("/me")
    assert resp.status_code == 200
    assert resp.json() == {"sub": "admin", "email": None, "name": None, "roles": ["rag-admin"]}


def test_me_with_expired_local_session_returns_401(pg_container: str) -> None:
    """TTL=1s → attendre → /me doit effacer le cookie et retourner local_session_expired."""
    client = _logged_local(pg_container, ttl_seconds=1)
    time.sleep(1.5)
    resp = client.get("/me")
    assert resp.status_code == 401
    assert resp.json()["error"] == "local_session_expired"


def test_me_with_no_session_returns_oidc_session_missing(pg_container: str) -> None:
    client = make_app_client(pg_container, password_hash="")
    resp = client.get("/me")
    assert resp.status_code == 401
    assert resp.json()["error"] == "oidc_session_missing"
