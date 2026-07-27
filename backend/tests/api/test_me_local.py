from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api._helpers import make_app_client

_USERNAME = "admin"
_EMAIL = "admin@example.com"
_PASSWORD = "test-pwd-local"


def _init_admin(client: TestClient) -> None:
    """Wizard init-admin : crée l'admin local et pose le cookie session."""
    resp = client.post(
        "/api/setup/init-admin",
        json={"username": _USERNAME, "email": _EMAIL, "password": _PASSWORD},
    )
    assert resp.status_code == 201, f"init-admin failed: {resp.json()}"


def test_me_with_local_session_returns_local_user(pg_container: str) -> None:
    # `with` obligatoire : le lifespan branche app.state.local_auth (et le pool).
    with make_app_client(pg_container) as client:
        _init_admin(client)
        resp = client.get("/me")
        assert resp.status_code == 200
        assert resp.json() == {
            "sub": _USERNAME,
            "email": None,
            "name": None,
            "roles": ["rag-admin"],
        }


def test_me_with_expired_local_session_returns_401(pg_container: str) -> None:
    """Session locale expirée → /me doit retourner local_session_expired.

    Le TTL est plafonné à >= 60 s côté Settings (ge=60) : impossible de
    passer 1 s par l'env. On injecte un TTL négatif directement dans le
    service pour créer une session déjà expirée, sans sleep.
    """
    with make_app_client(pg_container) as client:
        client.app.state.local_auth._ttl_seconds = -1
        _init_admin(client)
        resp = client.get("/me")
        assert resp.status_code == 401
        assert resp.json()["error"] == "local_session_expired"


def test_me_with_no_session_returns_oidc_session_missing(pg_container: str) -> None:
    with make_app_client(pg_container) as client:
        resp = client.get("/me")
        assert resp.status_code == 401
        assert resp.json()["error"] == "oidc_session_missing"
