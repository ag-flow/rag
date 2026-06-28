from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.api._helpers import make_app_client

_USERNAME = "admin"
_EMAIL = "admin@example.com"
_PASSWORD = "secure-password-123"


@pytest.fixture
def client(pg_container: str) -> TestClient:
    with make_app_client(pg_container) as c:
        yield c


# ──────────────────────────────────────────────
# GET /api/setup/status
# ──────────────────────────────────────────────


def test_setup_status_needs_setup_when_no_users(client: TestClient) -> None:
    resp = client.get("/api/setup/status")
    assert resp.status_code == 200
    assert resp.json() == {"needs_setup": True}


def test_setup_status_no_setup_needed_after_init(client: TestClient) -> None:
    client.post(
        "/api/setup/init-admin",
        json={"username": _USERNAME, "email": _EMAIL, "password": _PASSWORD},
    )
    resp = client.get("/api/setup/status")
    assert resp.status_code == 200
    assert resp.json() == {"needs_setup": False}


# ──────────────────────────────────────────────
# POST /api/setup/init-admin
# ──────────────────────────────────────────────


def test_init_admin_creates_user_and_returns_201(client: TestClient) -> None:
    resp = client.post(
        "/api/setup/init-admin",
        json={"username": _USERNAME, "email": _EMAIL, "password": _PASSWORD},
    )
    assert resp.status_code == 201
    assert resp.json() == {"ok": True}
    # Cookie de session posé automatiquement
    assert "session" in resp.cookies


def test_init_admin_sets_session_allowing_me(client: TestClient) -> None:
    client.post(
        "/api/setup/init-admin",
        json={"username": _USERNAME, "email": _EMAIL, "password": _PASSWORD},
    )
    me_resp = client.get("/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["sub"] == _USERNAME


def test_init_admin_second_call_returns_409(client: TestClient) -> None:
    client.post(
        "/api/setup/init-admin",
        json={"username": _USERNAME, "email": _EMAIL, "password": _PASSWORD},
    )
    resp = client.post(
        "/api/setup/init-admin",
        json={"username": "other", "email": "other@example.com", "password": _PASSWORD},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "setup_already_done"


def test_init_admin_short_password_returns_422(client: TestClient) -> None:
    resp = client.post(
        "/api/setup/init-admin",
        json={"username": _USERNAME, "email": _EMAIL, "password": "short"},
    )
    assert resp.status_code == 422


def test_init_admin_invalid_email_returns_422(client: TestClient) -> None:
    resp = client.post(
        "/api/setup/init-admin",
        json={"username": _USERNAME, "email": "not-an-email", "password": _PASSWORD},
    )
    assert resp.status_code == 422
