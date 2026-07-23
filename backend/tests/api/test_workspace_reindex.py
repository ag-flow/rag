from __future__ import annotations

import asyncio

import asyncpg
from fastapi.testclient import TestClient

from tests.api._helpers import make_ws_with_user_key


def _make_ws(
    client: TestClient,
    admin_headers: dict[str, str],
    name: str,
    *,
    scope: str = "read_write",
) -> str:
    _, api_key = make_ws_with_user_key(client, admin_headers, name, scope=scope)
    return api_key


def test_reindex_returns_202_and_enqueues_forced_job(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_reidx")
    r = admin_client.post(
        "/workspaces/ws_reidx/reindex/docs/foo.md",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"content": "hello world"},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert "job_id" in body
    assert "X-Correlation-ID" in r.headers

    async def check() -> None:
        conn = await asyncpg.connect(pg_container)
        try:
            row = await conn.fetchrow(
                "SELECT j.triggered_by, p.path, p.force "
                "FROM index_jobs j JOIN push_job_payloads p ON p.job_id=j.id "
                "WHERE j.id=$1::uuid",
                body["job_id"],
            )
        finally:
            await conn.close()
        assert row is not None
        assert row["triggered_by"] == "reindex_document"
        assert row["path"] == "docs/foo.md"
        assert row["force"] is True

    asyncio.run(check())


def test_reindex_read_scope_key_returns_401(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    read_key = _make_ws(admin_client, admin_headers, "ws_reidx_ro", scope="read")
    r = admin_client.post(
        "/workspaces/ws_reidx_ro/reindex/x.md",
        headers={"Authorization": f"Bearer {read_key}"},
        json={"content": "y"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


def test_reindex_requires_content(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_reidx_nc")
    r = admin_client.post(
        "/workspaces/ws_reidx_nc/reindex/x.md",
        headers={"Authorization": f"Bearer {api_key}"},
        json={},
    )
    assert r.status_code == 422
