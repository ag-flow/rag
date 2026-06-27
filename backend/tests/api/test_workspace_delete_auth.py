from __future__ import annotations

from fastapi.testclient import TestClient


def _make_ws(client: TestClient, admin_headers: dict[str, str], name: str) -> str:
    r = client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
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
    assert r.status_code == 201, r.text
    return r.json()["api_key"]


def test_delete_returns_401_for_unknown_workspace(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    r = admin_client.delete(
        "/workspaces/ghost/index/doc.md",
        headers={"Authorization": "Bearer nonexistent_key_xyz"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


def test_delete_returns_401_without_authorization(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_del_noauth")
    r = admin_client.delete("/workspaces/ws_del_noauth/index/doc.md")
    assert r.status_code == 401
    assert r.json()["detail"] == "missing_bearer_token"


def test_delete_returns_401_for_invalid_api_key(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_del_bad_key")
    r = admin_client.delete(
        "/workspaces/ws_del_bad_key/index/doc.md",
        headers={"Authorization": "Bearer not-the-real-key"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


def test_delete_returns_202_with_valid_api_key(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_del_ok")
    r = admin_client.delete(
        "/workspaces/ws_del_ok/index/docs/foo.md",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert "job_id" in body
    assert "X-Correlation-ID" in r.headers


def test_delete_cross_workspace_key_returns_401(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key_a = _make_ws(admin_client, admin_headers, "ws_del_a")
    _make_ws(admin_client, admin_headers, "ws_del_b")
    r = admin_client.delete(
        "/workspaces/ws_del_b/index/doc.md",
        headers={"Authorization": f"Bearer {key_a}"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


def test_delete_nested_path(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_del_nested")
    r = admin_client.delete(
        "/workspaces/ws_del_nested/index/a/b/c/deep.md",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert r.status_code == 202, r.text
