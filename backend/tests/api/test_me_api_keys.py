from __future__ import annotations

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


def test_workspace_creation_no_longer_returns_api_key(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    ws = _create_ws(admin_client, admin_headers, "meapikeys-a")
    assert "api_key" not in ws


def test_create_list_rotate_revoke_user_key(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    ws = _create_ws(admin_client, admin_headers, "meapikeys-b")

    # Création avec un grant read+write — la clé n'apparaît qu'ici.
    created = admin_client.post(
        "/api/me/api-keys",
        headers=admin_headers,
        json={
            "name": "ma-cle",
            "workspaces": [
                {"workspace_id": ws["id"], "can_read": True, "can_write": True}
            ],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["api_key"]
    key_id = body["id"]

    # Liste : statut actif, grant présent avec permissions, pas de valeur en clair.
    listed = admin_client.get("/api/me/api-keys", headers=admin_headers).json()
    entry = next(k for k in listed if k["id"] == key_id)
    assert entry["status"] == "active"
    assert "api_key" not in entry
    grant = entry["workspaces"][0]
    assert grant["workspace_name"] == "meapikeys-b"
    assert grant["can_read"] is True and grant["can_write"] is True

    # Rotation : nouvelle clé + grâce, les grants sont hérités.
    rotated = admin_client.post(
        f"/api/me/api-keys/{key_id}/rotate", headers=admin_headers
    )
    assert rotated.status_code == 200
    new_id = rotated.json()["new_key_id"]
    listed = admin_client.get("/api/me/api-keys", headers=admin_headers).json()
    old_entry = next(k for k in listed if k["id"] == key_id)
    new_entry = next(k for k in listed if k["id"] == new_id)
    assert old_entry["status"] == "grace_period"
    assert new_entry["workspaces"][0]["workspace_name"] == "meapikeys-b"

    # Révocation.
    assert (
        admin_client.delete(f"/api/me/api-keys/{new_id}", headers=admin_headers)
    ).status_code == 204
    listed = admin_client.get("/api/me/api-keys", headers=admin_headers).json()
    assert next(k for k in listed if k["id"] == new_id)["status"] == "revoked"


def test_update_grants_replaces_permissions(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    ws = _create_ws(admin_client, admin_headers, "meapikeys-c")
    key = admin_client.post(
        "/api/me/api-keys",
        headers=admin_headers,
        json={"name": "cle-grants", "workspaces": []},
    ).json()

    resp = admin_client.put(
        f"/api/me/api-keys/{key['id']}/workspaces",
        headers=admin_headers,
        json={
            "workspaces": [
                {"workspace_id": ws["id"], "can_read": True, "can_write": False}
            ]
        },
    )
    assert resp.status_code == 204
    listed = admin_client.get("/api/me/api-keys", headers=admin_headers).json()
    grant = next(k for k in listed if k["id"] == key["id"])["workspaces"][0]
    assert grant["can_read"] is True and grant["can_write"] is False


def test_create_key_unknown_workspace_422(
    admin_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    resp = admin_client.post(
        "/api/me/api-keys",
        headers=admin_headers,
        json={
            "name": "cle-ghost",
            "workspaces": [
                {
                    "workspace_id": "00000000-0000-0000-0000-000000000000",
                    "can_read": True,
                    "can_write": False,
                }
            ],
        },
    )
    assert resp.status_code == 422
