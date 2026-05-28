from __future__ import annotations

import asyncio

import asyncpg
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
    assert r.status_code == 201
    return r.json()["api_key"]


def test_push_returns_202_with_job_id(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_async1")
    headers = {"Authorization": f"Bearer {api_key}"}

    r = admin_client.post(
        "/workspaces/ws_async1/index",
        headers=headers,
        json={"path": "doc.md", "content": "hello world"},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "pending"
    assert "job_id" in body
    assert "X-Correlation-ID" in r.headers


def test_push_payload_stored_in_db(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_async2")
    headers = {"Authorization": f"Bearer {api_key}"}

    r = admin_client.post(
        "/workspaces/ws_async2/index",
        headers=headers,
        json={"path": "a.md", "content": "stored content"},
    )
    assert r.status_code == 202
    job_id = r.json()["job_id"]

    async def check() -> None:
        conn = await asyncpg.connect(pg_container)
        try:
            row = await conn.fetchrow(
                "SELECT path, content FROM push_job_payloads WHERE job_id=$1::uuid", job_id
            )
            assert row is not None
            assert row["path"] == "a.md"
            assert row["content"] == "stored content"
        finally:
            await conn.close()

    asyncio.get_event_loop().run_until_complete(check())


def test_push_two_requests_create_two_jobs(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    """Two pushes create two independent jobs (no dedup at endpoint level)."""
    api_key = _make_ws(admin_client, admin_headers, "ws_async3")
    headers = {"Authorization": f"Bearer {api_key}"}

    r1 = admin_client.post(
        "/workspaces/ws_async3/index",
        headers=headers,
        json={"path": "doc.md", "content": "same content"},
    )
    r2 = admin_client.post(
        "/workspaces/ws_async3/index",
        headers=headers,
        json={"path": "doc.md", "content": "same content"},
    )
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json()["job_id"] != r2.json()["job_id"]
    assert r1.headers["X-Correlation-ID"] != r2.headers["X-Correlation-ID"]
