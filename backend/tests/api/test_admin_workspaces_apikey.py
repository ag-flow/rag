from __future__ import annotations

import re

from fastapi.testclient import TestClient


def _create_ws(client: TestClient, headers: dict[str, str], name: str) -> dict:
    resp = client.post(
        "/api/admin/workspaces",
        headers=headers,
        json={
            "name": name,
            "api_key_vault": "rag",
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert resp.status_code == 201
    return resp.json()


def test_get_apikey_returns_stored_key(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    """GET /workspaces/{name}/apikey retourne la clé générée à la création."""
    created = _create_ws(admin_client, admin_headers, "ws_get")
    expected_key = created["api_key"]
    assert re.fullmatch(r"[A-Za-z0-9_-]{48}", expected_key)

    r = admin_client.get("/api/admin/workspaces/ws_get/apikey", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["api_key"] == expected_key


def test_get_apikey_is_idempotent(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    """Deux GET successifs retournent la même valeur (idempotence)."""
    _create_ws(admin_client, admin_headers, "ws_idem")

    r1 = admin_client.get("/api/admin/workspaces/ws_idem/apikey", headers=admin_headers)
    r2 = admin_client.get("/api/admin/workspaces/ws_idem/apikey", headers=admin_headers)
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["api_key"] == r2.json()["api_key"]


def test_get_apikey_reflects_rotation(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    """GET après rotate retourne la nouvelle clé (pas l'ancienne)."""
    _create_ws(admin_client, admin_headers, "ws_rot_get")

    before = admin_client.get("/api/admin/workspaces/ws_rot_get/apikey", headers=admin_headers).json()["api_key"]
    rotated = admin_client.post("/api/admin/workspaces/ws_rot_get/rotate-apikey", headers=admin_headers).json()["api_key"]
    after = admin_client.get("/api/admin/workspaces/ws_rot_get/apikey", headers=admin_headers).json()["api_key"]

    assert before != after
    assert rotated == after


def test_get_apikey_404_when_workspace_missing(
    admin_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    """GET sur un workspace inexistant retourne 404."""
    r = admin_client.get("/api/admin/workspaces/does_not_exist/apikey", headers=admin_headers)
    assert r.status_code == 404


def test_get_apikey_401_without_auth(admin_client: TestClient) -> None:
    """Le routeur admin est protégé — sans Bearer, 401."""
    r = admin_client.get("/api/admin/workspaces/whatever/apikey")
    assert r.status_code == 401
