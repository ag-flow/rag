from __future__ import annotations

import time

from fastapi.testclient import TestClient

from tests.api._helpers import make_app_client

_USERNAME = "admin"
_EMAIL = "admin@example.com"
_PASSWORD = "test-pwd-local"


def _logged_local(pg_container: str, ttl_seconds: int = 28800) -> TestClient:
    """TestClient auto-connecté via le wizard init-admin + login."""
    client = make_app_client(pg_container, ttl_seconds=ttl_seconds)
    resp = client.post(
        "/api/setup/init-admin",
        json={"username": _USERNAME, "email": _EMAIL, "password": _PASSWORD},
    )
    assert resp.status_code == 201, f"init-admin failed: {resp.json()}"
    return client


def test_me_with_local_session_returns_local_user(pg_container: str) -> None:
    client = _logged_local(pg_container)
    resp = client.get("/me")
    assert resp.status_code == 200
    assert resp.json() == {"sub": _USERNAME, "email": None, "name": None, "roles": ["rag-admin"]}


def test_me_with_expired_local_session_returns_401(pg_container: str) -> None:
    """TTL=1s → attendre → /me doit effacer le cookie et retourner local_session_expired."""
    client = _logged_local(pg_container, ttl_seconds=1)
    time.sleep(1.5)
    resp = client.get("/me")
    assert resp.status_code == 401
    assert resp.json()["error"] == "local_session_expired"


def test_me_with_no_session_returns_oidc_session_missing(pg_container: str) -> None:
    client = make_app_client(pg_container)
    resp = client.get("/me")
    assert resp.status_code == 401
    assert resp.json()["error"] == "oidc_session_missing"
