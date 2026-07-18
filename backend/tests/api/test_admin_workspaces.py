from __future__ import annotations

import os

from fastapi.testclient import TestClient

from tests.api.conftest import seed_endpoint_sync


def _create_ws(client: TestClient, headers: dict[str, str], name: str) -> dict:
    return client.post(
        "/api/admin/workspaces",
        headers=headers,
        json={"name": name, "endpoint_id": client.default_endpoint_id},
    ).json()


def test_post_workspaces_201_no_api_key_in_response(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    """La création ne retourne plus de clé : elles sont au niveau utilisateur."""
    r = admin_client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={"name": "ws_e2e_a", "endpoint_id": admin_client.default_endpoint_id},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "ws_e2e_a"
    assert "api_key" not in body


def test_post_workspaces_401_without_bearer(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/api/admin/workspaces",
        json={"name": "x", "endpoint_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert r.status_code == 401


def test_post_workspaces_422_unknown_model(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={
            "name": "ws_unknown_model",
            "endpoint_id": seed_endpoint_sync(
                os.environ["DATABASE_URL"],
                slug="ep-nope",
                provider="nope",
                model="nope",
                api_key_ref="k",
            ),
        },
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "model_not_supported"


# test_post_workspaces_422_ref_not_in_vault supprimé : la validation eager de
# l'api_key_ref à la création n'existe plus — la ref vient du préréglage
# d'endpoint du coffre (chantier endpoints/clés user) ; l'eager validation ne
# subsiste que sur PATCH (couvert par les tests patch ci-dessous).


def test_post_workspaces_409_duplicate(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _create_ws(admin_client, admin_headers, "ws_dup_e2e")
    r = admin_client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={"name": "ws_dup_e2e", "endpoint_id": admin_client.default_endpoint_id},
    )
    assert r.status_code == 409
    assert r.json()["error"] == "workspace_already_exists"


def test_get_workspaces_list(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _create_ws(admin_client, admin_headers, "ws_list_e2e_1")
    _create_ws(admin_client, admin_headers, "ws_list_e2e_2")
    r = admin_client.get("/api/admin/workspaces", headers=admin_headers)
    assert r.status_code == 200
    names = {ws["name"] for ws in r.json()}
    assert {"ws_list_e2e_1", "ws_list_e2e_2"}.issubset(names)


def test_get_workspace_detail_404(admin_client: TestClient, admin_headers: dict[str, str]) -> None:
    r = admin_client.get("/api/admin/workspaces/missing", headers=admin_headers)
    assert r.status_code == 404
    assert r.json() == {"error": "workspace_not_found", "name": "missing"}


def test_patch_workspace_updates_api_key_ref(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _create_ws(admin_client, admin_headers, "ws_patch_e2e")
    r = admin_client.patch(
        "/api/admin/workspaces/ws_patch_e2e",
        headers=admin_headers,
        json={"indexer": {"api_key_ref": "voyage_api_key"}},
    )
    assert r.status_code == 200
    assert r.json()["indexer"]["api_key_ref"] == "voyage_api_key"


def test_delete_workspace_204(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _create_ws(admin_client, admin_headers, "ws_del_e2e")
    r = admin_client.delete("/api/admin/workspaces/ws_del_e2e", headers=admin_headers)
    assert r.status_code == 204
    r2 = admin_client.delete("/api/admin/workspaces/ws_del_e2e", headers=admin_headers)
    assert r2.status_code == 404
