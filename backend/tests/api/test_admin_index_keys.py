# backend/tests/api/test_admin_index_keys.py
from __future__ import annotations

import asyncio
import os

import asyncpg
from fastapi.testclient import TestClient

from tests.api.conftest import seed_endpoint_sync


def _create_ws(client: TestClient, headers: dict[str, str], name: str) -> dict:
    r = client.post(
        "/api/admin/workspaces",
        headers=headers,
        json={
            "name": name,
            "endpoint_id": seed_endpoint_sync(
                os.environ["DATABASE_URL"],
                slug="ep-ollama-stub",
                provider="ollama",
                model="mxbai-embed-large",
                api_key_ref=None,
                base_url="http://stub:11434",
            ),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _insert_doc(workspace_name: str, path: str = "LESSONS.md") -> None:
    async def _go() -> None:
        conn = await asyncpg.connect(os.environ["DATABASE_URL"])
        try:
            ws_id = await conn.fetchval("SELECT id FROM workspaces WHERE name=$1", workspace_name)
            await conn.execute(
                "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
                "VALUES ($1, $2, 'sha256:0', 'ollama/mxbai-embed-large')",
                ws_id,
                path,
            )
        finally:
            await conn.close()

    # Python 3.12 : get_event_loop() hors boucle courante renvoie une boucle
    # fermée par pytest-asyncio → RuntimeError. Boucle dédiée via asyncio.run.
    asyncio.run(_go())


def test_get_index_keys_empty(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    _create_ws(admin_client, admin_headers, "ws_ik_empty")
    r = admin_client.get("/api/admin/workspaces/ws_ik_empty/index-keys", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["paths"] == []


def test_get_index_keys_lists_paths(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    _create_ws(admin_client, admin_headers, "ws_ik_paths")
    _insert_doc("ws_ik_paths", "LESSONS.md")
    _insert_doc("ws_ik_paths", "docs/api.md")

    r = admin_client.get("/api/admin/workspaces/ws_ik_paths/index-keys", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    paths = [e["path"] for e in body["paths"]]
    assert "LESSONS.md" in paths
    assert "docs/api.md" in paths


def test_get_index_keys_default_strategy_replace(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    _create_ws(admin_client, admin_headers, "ws_ik_defstrat")
    _insert_doc("ws_ik_defstrat", "README.md")

    r = admin_client.get("/api/admin/workspaces/ws_ik_defstrat/index-keys", headers=admin_headers)
    assert r.status_code == 200
    entry = r.json()["paths"][0]
    assert entry["strategy"] == "replace"
    assert entry["updated_by"] == "ui"


def test_patch_strategy_and_read_back(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    _create_ws(admin_client, admin_headers, "ws_ik_patch")
    _insert_doc("ws_ik_patch", "LESSONS.md")

    r = admin_client.patch(
        "/api/admin/workspaces/ws_ik_patch/index-keys/LESSONS.md/strategy",
        headers=admin_headers,
        json={"strategy": "append"},
    )
    assert r.status_code == 204

    r2 = admin_client.get("/api/admin/workspaces/ws_ik_patch/index-keys", headers=admin_headers)
    entry = next(e for e in r2.json()["paths"] if e["path"] == "LESSONS.md")
    assert entry["strategy"] == "append"
    assert entry["updated_by"] == "ui"


def test_patch_strategy_idempotent(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    _create_ws(admin_client, admin_headers, "ws_ik_idem")
    _insert_doc("ws_ik_idem", "LESSONS.md")

    for _ in range(2):
        r = admin_client.patch(
            "/api/admin/workspaces/ws_ik_idem/index-keys/LESSONS.md/strategy",
            headers=admin_headers,
            json={"strategy": "append"},
        )
        assert r.status_code == 204


def test_get_index_keys_404_unknown_workspace(
    admin_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    r = admin_client.get("/api/admin/workspaces/nonexistent/index-keys", headers=admin_headers)
    assert r.status_code == 404


def test_patch_strategy_422_invalid_value(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    _create_ws(admin_client, admin_headers, "ws_ik_422")
    r = admin_client.patch(
        "/api/admin/workspaces/ws_ik_422/index-keys/LESSONS.md/strategy",
        headers=admin_headers,
        json={"strategy": "invalid"},
    )
    assert r.status_code == 422
