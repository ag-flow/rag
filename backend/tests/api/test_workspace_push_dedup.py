from __future__ import annotations

import asyncio

import asyncpg
from fastapi.testclient import TestClient

from tests.api._helpers import make_ws_with_user_key


def _make_ws(client: TestClient, admin_headers: dict[str, str], name: str) -> str:
    """Crée un workspace + clé utilisateur avec grant d'écriture → clé claire."""
    _, api_key = make_ws_with_user_key(client, admin_headers, name)
    return api_key


def test_push_returns_202_with_job_id(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_async1")
    headers = {"Authorization": f"Bearer {api_key}"}

    r = admin_client.post(
        "/index",
        headers=headers,
        json={"workspace": "ws_async1", "path": "doc.md", "content": "hello world"},
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
        "/index",
        headers=headers,
        json={"workspace": "ws_async2", "path": "a.md", "content": "stored content"},
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

    asyncio.run(check())


def test_push_two_requests_create_two_jobs(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    """Two pushes create two independent jobs (no dedup at endpoint level)."""
    api_key = _make_ws(admin_client, admin_headers, "ws_async3")
    headers = {"Authorization": f"Bearer {api_key}"}

    r1 = admin_client.post(
        "/index",
        headers=headers,
        json={"workspace": "ws_async3", "path": "doc.md", "content": "same content"},
    )
    r2 = admin_client.post(
        "/index",
        headers=headers,
        json={"workspace": "ws_async3", "path": "doc.md", "content": "same content"},
    )
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json()["job_id"] != r2.json()["job_id"]
    assert r1.headers["X-Correlation-ID"] != r2.headers["X-Correlation-ID"]
