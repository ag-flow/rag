from __future__ import annotations

from fastapi.testclient import TestClient


def _create_ws(client: TestClient, headers: dict[str, str], name: str) -> dict:
    resp = client.post(
        "/api/admin/workspaces",
        headers=headers,
        json={"name": name, "label": name, "endpoint_id": client.default_endpoint_id},
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
    _create_ws(admin_client, admin_headers, "meapikeys-b")

    # Création avec un niveau read_write — la clé n'apparaît qu'ici.
    created = admin_client.post(
        "/api/me/api-keys",
        headers=admin_headers,
        json={"name": "ma-cle", "scope": "read_write"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["api_key"]
    assert body["scope"] == "read_write"
    key_id = body["id"]

    # Liste : statut actif, scope présent, pas de valeur en clair.
    listed = admin_client.get("/api/me/api-keys", headers=admin_headers).json()
    entry = next(k for k in listed if k["id"] == key_id)
    assert entry["status"] == "active"
    assert "api_key" not in entry
    assert entry["scope"] == "read_write"

    # Rotation : nouvelle clé + grâce, le niveau d'accès est hérité.
    rotated = admin_client.post(
        f"/api/me/api-keys/{key_id}/rotate", headers=admin_headers
    )
    assert rotated.status_code == 200
    new_id = rotated.json()["new_key_id"]
    listed = admin_client.get("/api/me/api-keys", headers=admin_headers).json()
    old_entry = next(k for k in listed if k["id"] == key_id)
    new_entry = next(k for k in listed if k["id"] == new_id)
    assert old_entry["status"] == "grace_period"
    assert new_entry["scope"] == "read_write"

    # Révocation.
    assert (
        admin_client.delete(f"/api/me/api-keys/{new_id}", headers=admin_headers)
    ).status_code == 204
    listed = admin_client.get("/api/me/api-keys", headers=admin_headers).json()
    assert next(k for k in listed if k["id"] == new_id)["status"] == "revoked"


def test_update_scope_replaces_level(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    key = admin_client.post(
        "/api/me/api-keys",
        headers=admin_headers,
        json={"name": "cle-scope", "scope": "read"},
    ).json()

    resp = admin_client.put(
        f"/api/me/api-keys/{key['id']}/scope",
        headers=admin_headers,
        json={"scope": "admin"},
    )
    assert resp.status_code == 204
    listed = admin_client.get("/api/me/api-keys", headers=admin_headers).json()
    entry = next(k for k in listed if k["id"] == key["id"])
    assert entry["scope"] == "admin"


def test_update_scope_unknown_key_404(
    admin_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    resp = admin_client.put(
        "/api/me/api-keys/00000000-0000-0000-0000-000000000000/scope",
        headers=admin_headers,
        json={"scope": "read_write"},
    )
    assert resp.status_code == 404


def test_create_key_invalid_scope_422(
    admin_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    resp = admin_client.post(
        "/api/me/api-keys",
        headers=admin_headers,
        json={"name": "cle-bad-scope", "scope": "superuser"},
    )
    assert resp.status_code == 422
