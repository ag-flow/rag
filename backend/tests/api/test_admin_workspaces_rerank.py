from __future__ import annotations

from fastapi.testclient import TestClient


def _create_workspace(client: TestClient, admin_headers: dict[str, str], name: str) -> None:
    r = client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={
            "name": name,
            "api_key_vault": "rag",
            "indexer": {
                "provider": "ollama", "model": "mxbai-embed-large",
                "api_key_ref": None,
            },
        },
    )
    assert r.status_code == 201, r.text


def test_get_rerank_returns_404_when_not_configured(
    admin_client: TestClient, admin_headers: dict[str, str],
) -> None:
    _create_workspace(admin_client, admin_headers, "ws_get_no_rerank")
    r = admin_client.get(
        "/api/admin/workspaces/ws_get_no_rerank/rerank",
        headers=admin_headers,
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "rerank_not_configured"


def test_get_rerank_returns_404_when_workspace_missing(
    admin_client: TestClient, admin_headers: dict[str, str],
) -> None:
    r = admin_client.get(
        "/api/admin/workspaces/no_such_ws/rerank",
        headers=admin_headers,
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "workspace_not_found"


def test_put_rerank_creates_config(
    admin_client: TestClient, admin_headers: dict[str, str],
) -> None:
    _create_workspace(admin_client, admin_headers, "ws_put_rerank")
    r = admin_client.put(
        "/api/admin/workspaces/ws_put_rerank/rerank",
        headers=admin_headers,
        json={
            "provider": "ollama", "model": "bge-reranker-v2-m3",
            "api_key_ref": None, "base_url": "http://localhost:11434",
            "top_k_pre_rerank": 50,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "ollama"
    assert body["top_k_pre_rerank"] == 50


def test_put_rerank_upsert_idempotent(
    admin_client: TestClient, admin_headers: dict[str, str],
) -> None:
    _create_workspace(admin_client, admin_headers, "ws_idem_rerank")
    payload = {
        "provider": "ollama", "model": "bge",
        "api_key_ref": None, "base_url": "http://localhost:11434",
        "top_k_pre_rerank": 50,
    }
    r1 = admin_client.put(
        "/api/admin/workspaces/ws_idem_rerank/rerank",
        headers=admin_headers, json=payload,
    )
    r2 = admin_client.put(
        "/api/admin/workspaces/ws_idem_rerank/rerank",
        headers=admin_headers, json={**payload, "top_k_pre_rerank": 100},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["top_k_pre_rerank"] == 100


def test_delete_rerank_204(
    admin_client: TestClient, admin_headers: dict[str, str],
) -> None:
    _create_workspace(admin_client, admin_headers, "ws_del_rerank")
    admin_client.put(
        "/api/admin/workspaces/ws_del_rerank/rerank",
        headers=admin_headers,
        json={
            "provider": "ollama", "model": "bge",
            "api_key_ref": None, "base_url": "http://localhost:11434",
            "top_k_pre_rerank": 50,
        },
    )
    r = admin_client.delete(
        "/api/admin/workspaces/ws_del_rerank/rerank",
        headers=admin_headers,
    )
    assert r.status_code == 204


def test_delete_rerank_idempotent_when_absent(
    admin_client: TestClient, admin_headers: dict[str, str],
) -> None:
    _create_workspace(admin_client, admin_headers, "ws_del_absent")
    r = admin_client.delete(
        "/api/admin/workspaces/ws_del_absent/rerank",
        headers=admin_headers,
    )
    assert r.status_code == 204
