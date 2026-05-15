from __future__ import annotations

from fastapi.testclient import TestClient


def test_admin_routes_require_master_key(admin_client: TestClient) -> None:
    r = admin_client.get("/workspaces")
    assert r.status_code == 401
    assert r.json()["detail"] == "missing_bearer_token"


def test_admin_routes_accept_valid_master_key(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.get("/workspaces", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_admin_error_handlers_registered(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.get("/workspaces/absent", headers=admin_headers)
    assert r.status_code == 404
    assert r.json() == {"error": "workspace_not_found", "name": "absent"}
