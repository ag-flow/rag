from __future__ import annotations

import re

from fastapi.testclient import TestClient


def _create_ws(client: TestClient, headers: dict[str, str], name: str) -> dict:
    return client.post(
        "/workspaces",
        headers=headers,
        json={
            "name": name,
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    ).json()


def test_post_workspaces_201_returns_api_key_once(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    r = admin_client.post(
        "/workspaces",
        headers=admin_headers,
        json={
            "name": "ws_e2e_a",
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "ws_e2e_a"
    assert re.fullmatch(r"[A-Za-z0-9_-]{48}", body["api_key"])


def test_post_workspaces_401_without_bearer(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/workspaces", json={"name": "x", "indexer": {"provider": "p", "model": "m"}}
    )
    assert r.status_code == 401


def test_post_workspaces_422_unknown_model(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.post(
        "/workspaces",
        headers=admin_headers,
        json={
            "name": "ws_unknown_model",
            "indexer": {"provider": "nope", "model": "nope", "api_key_ref": "k"},
        },
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "model_not_supported"


def test_post_workspaces_422_ref_not_in_vault(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.post(
        "/workspaces",
        headers=admin_headers,
        json={
            "name": "ws_bad_ref",
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "unknown_ref",
            },
        },
    )
    assert r.status_code == 422
    assert r.json()["error"] == "ref_not_found_in_vault"


def test_post_workspaces_409_duplicate(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _create_ws(admin_client, admin_headers, "ws_dup_e2e")
    r = admin_client.post(
        "/workspaces",
        headers=admin_headers,
        json={
            "name": "ws_dup_e2e",
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 409
    assert r.json()["error"] == "workspace_already_exists"


def test_get_workspaces_list(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _create_ws(admin_client, admin_headers, "ws_list_e2e_1")
    _create_ws(admin_client, admin_headers, "ws_list_e2e_2")
    r = admin_client.get("/workspaces", headers=admin_headers)
    assert r.status_code == 200
    names = {ws["name"] for ws in r.json()}
    assert {"ws_list_e2e_1", "ws_list_e2e_2"}.issubset(names)


def test_get_workspace_detail_404(admin_client: TestClient, admin_headers: dict[str, str]) -> None:
    r = admin_client.get("/workspaces/missing", headers=admin_headers)
    assert r.status_code == 404
    assert r.json() == {"error": "workspace_not_found", "name": "missing"}


def test_patch_workspace_updates_api_key_ref(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _create_ws(admin_client, admin_headers, "ws_patch_e2e")
    r = admin_client.patch(
        "/workspaces/ws_patch_e2e",
        headers=admin_headers,
        json={"indexer": {"api_key_ref": "voyage_api_key"}},
    )
    assert r.status_code == 200
    assert r.json()["indexer"]["api_key_ref"] == "voyage_api_key"


def test_delete_workspace_204(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _create_ws(admin_client, admin_headers, "ws_del_e2e")
    r = admin_client.delete("/workspaces/ws_del_e2e", headers=admin_headers)
    assert r.status_code == 204
    r2 = admin_client.delete("/workspaces/ws_del_e2e", headers=admin_headers)
    assert r2.status_code == 404


def test_rotate_apikey_returns_new_key(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    create = _create_ws(admin_client, admin_headers, "ws_rotate_e2e")
    old = create["api_key"]
    r = admin_client.post("/workspaces/ws_rotate_e2e/rotate-apikey", headers=admin_headers)
    assert r.status_code == 200
    new = r.json()["api_key"]
    assert new != old
    assert re.fullmatch(r"[A-Za-z0-9_-]{48}", new)
