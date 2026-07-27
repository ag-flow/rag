from __future__ import annotations

from fastapi.testclient import TestClient


def _setup_ws_with_doc(client: TestClient, headers: dict[str, str], name: str) -> None:
    client.post(
        "/api/admin/workspaces",
        headers=headers,
        json={"name": name, "label": name, "endpoint_id": client.default_endpoint_id},
    )
    import asyncio
    import os

    import asyncpg

    async def _insert_doc() -> None:
        conn = await asyncpg.connect(os.environ["DATABASE_URL"])
        try:
            ws_id = await conn.fetchval("SELECT id FROM workspaces WHERE name=$1", name)
            await conn.execute(
                "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
                "VALUES ($1, 'a.md', 'sha256:abc', 'openai/text-embedding-3-small')",
                ws_id,
            )
        finally:
            await conn.close()

    # Python 3.12 : get_event_loop() hors boucle courante renvoie une boucle
    # fermée par pytest-asyncio → RuntimeError. Boucle dédiée via asyncio.run.
    asyncio.run(_insert_doc())


def test_post_reindex_no_change_202_pending(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _setup_ws_with_doc(admin_client, admin_headers, "ws_re_e2e_a")
    r = admin_client.post("/api/admin/workspaces/ws_re_e2e_a/reindex", headers=admin_headers)
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "pending"
    assert body["triggered_by"] == "manual"


def test_post_reindex_indexer_change_409_without_confirm(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _setup_ws_with_doc(admin_client, admin_headers, "ws_re_e2e_b")
    r = admin_client.post(
        "/api/admin/workspaces/ws_re_e2e_b/reindex",
        headers=admin_headers,
        json={
            "indexer": {
                "provider": "voyage",
                "model": "voyage-3",
                "api_key_ref": "voyage_api_key",
            }
        },
    )
    assert r.status_code == 409
    body = r.json()
    assert body["error"] == "indexer_change_requires_reindex"
    assert body["documents_count"] == 1


def test_post_reindex_indexer_change_with_confirm_202(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _setup_ws_with_doc(admin_client, admin_headers, "ws_re_e2e_c")
    r = admin_client.post(
        "/api/admin/workspaces/ws_re_e2e_c/reindex?confirm=true",
        headers=admin_headers,
        json={
            "indexer": {
                "provider": "voyage",
                "model": "voyage-3",
                "api_key_ref": "voyage_api_key",
            }
        },
    )
    assert r.status_code == 202
    assert r.json()["triggered_by"] == "reindex_indexer_change"


def test_get_jobs_lists_pending(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _setup_ws_with_doc(admin_client, admin_headers, "ws_re_e2e_d")
    admin_client.post("/api/admin/workspaces/ws_re_e2e_d/reindex", headers=admin_headers)
    r = admin_client.get("/api/admin/workspaces/ws_re_e2e_d/jobs", headers=admin_headers)
    assert r.status_code == 200
    jobs = r.json()
    assert len(jobs) >= 1
    assert jobs[0]["status"] == "pending"


def test_get_job_status_single_returns_200(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    """A1 : statut d'un job unique côté API admin (parité MCP/Bearer)."""
    _setup_ws_with_doc(admin_client, admin_headers, "ws_re_e2e_single")
    admin_client.post("/api/admin/workspaces/ws_re_e2e_single/reindex", headers=admin_headers)
    jobs = admin_client.get(
        "/api/admin/workspaces/ws_re_e2e_single/jobs", headers=admin_headers
    ).json()
    job_id = jobs[0]["id"]

    r = admin_client.get(
        f"/api/admin/workspaces/ws_re_e2e_single/jobs/{job_id}", headers=admin_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == job_id


def test_get_job_status_unknown_returns_404(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _setup_ws_with_doc(admin_client, admin_headers, "ws_re_e2e_404")
    r = admin_client.get(
        "/api/admin/workspaces/ws_re_e2e_404/jobs/00000000-0000-0000-0000-000000000000",
        headers=admin_headers,
    )
    assert r.status_code == 404
    assert r.json()["error"] == "job_not_found"
