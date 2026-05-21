from __future__ import annotations

from fastapi.testclient import TestClient


def _setup_ws(client: TestClient, headers: dict[str, str], name: str) -> None:
    client.post(
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


def test_post_source_201(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _setup_ws(admin_client, admin_headers, "ws_src_e2e_a")
    r = admin_client.post(
        "/api/admin/workspaces/ws_src_e2e_a/sources",
        headers=admin_headers,
        json={
            "type": "git",
            "config": {
                "url": "https://github.com/x/y",
                "branch": "main",
                "auth_ref": "github_token",
            },
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["type"] == "git"
    assert body["config"]["url"] == "https://github.com/x/y"


def test_post_source_404_workspace_not_found(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.post(
        "/api/admin/workspaces/absent/sources",
        headers=admin_headers,
        json={"type": "git", "config": {"url": "https://x/y"}},
    )
    assert r.status_code == 404


def test_post_source_422_non_git(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _setup_ws(admin_client, admin_headers, "ws_src_e2e_b")
    r = admin_client.post(
        "/api/admin/workspaces/ws_src_e2e_b/sources",
        headers=admin_headers,
        json={"type": "confluence", "config": {"url": "https://wiki.example.com"}},
    )
    assert r.status_code == 422


def test_delete_source_204(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _setup_ws(admin_client, admin_headers, "ws_src_e2e_c")
    create = admin_client.post(
        "/api/admin/workspaces/ws_src_e2e_c/sources",
        headers=admin_headers,
        json={
            "type": "git",
            "config": {"url": "https://x/y", "auth_ref": "github_token"},
        },
    ).json()
    r = admin_client.delete(
        f"/api/admin/workspaces/ws_src_e2e_c/sources/{create['id']}", headers=admin_headers
    )
    assert r.status_code == 204


def test_delete_source_404_unknown_id(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    import uuid

    _setup_ws(admin_client, admin_headers, "ws_src_e2e_d")
    r = admin_client.delete(
        f"/api/admin/workspaces/ws_src_e2e_d/sources/{uuid.uuid4()}", headers=admin_headers
    )
    assert r.status_code == 404
