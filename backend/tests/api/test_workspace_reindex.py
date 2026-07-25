from __future__ import annotations

import asyncio

import asyncpg
from fastapi.testclient import TestClient

from tests.api._helpers import make_ws_with_user_key

# Ré-évaluation unifiée : plus d'endpoint /reindex/{path} distinct — c'est
# POST /index avec `force: true` (path dans le corps).


def _make_ws(
    client: TestClient,
    admin_headers: dict[str, str],
    name: str,
    *,
    scope: str = "read_write",
) -> str:
    _, api_key = make_ws_with_user_key(client, admin_headers, name, scope=scope)
    return api_key


def test_index_force_enqueues_reindex_job(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_reidx")
    r = admin_client.post(
        "/api/v1/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "workspace": "ws_reidx",
            "path": "docs/foo.md",
            "content": "hello world",
            "force": True,
        },
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

    async def check_params() -> None:
        conn = await asyncpg.connect(pg_container)
        try:
            raw = await conn.fetchval(
                "SELECT params FROM index_jobs WHERE id=$1::uuid", body["job_id"]
            )
        finally:
            await conn.close()
        import json

        params = json.loads(raw)
        # Instantané de la demande : consultable même après purge du payload.
        assert params["force"] is True
        assert params["content_bytes"] == len(b"hello world")
        assert "correlation_id" in params

    asyncio.run(check_params())

    asyncio.run(check())


def test_index_without_force_is_plain_push(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    """Sans force (défaut) : c'est un push classique, dédup-gardé."""
    api_key = _make_ws(admin_client, admin_headers, "ws_idx_plain")
    r = admin_client.post(
        "/api/v1/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"workspace": "ws_idx_plain", "path": "a.md", "content": "hello"},
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]

    async def check() -> None:
        conn = await asyncpg.connect(pg_container)
        try:
            row = await conn.fetchrow(
                "SELECT j.triggered_by, p.force "
                "FROM index_jobs j JOIN push_job_payloads p ON p.job_id=j.id "
                "WHERE j.id=$1::uuid",
                job_id,
            )
        finally:
            await conn.close()
        assert row["triggered_by"] == "push"
        assert row["force"] is False

    asyncio.run(check())


def test_index_read_scope_key_returns_401(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    read_key = _make_ws(admin_client, admin_headers, "ws_reidx_ro", scope="read")
    r = admin_client.post(
        "/api/v1/index",
        headers={"Authorization": f"Bearer {read_key}"},
        json={"workspace": "ws_reidx_ro", "path": "x.md", "content": "y", "force": True},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


def test_index_requires_content(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_reidx_nc")
    r = admin_client.post(
        "/api/v1/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"workspace": "ws_reidx_nc", "path": "x.md", "force": True},
    )
    assert r.status_code == 422


def test_index_stores_source_url(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_reidx_url")
    r = admin_client.post(
        "/api/v1/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "workspace": "ws_reidx_url",
            "path": "docs/foo.md",
            "content": "hello",
            "force": True,
            "source_url": "https://docs.example/foo?k=1",
        },
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]

    async def _check() -> None:
        conn = await asyncpg.connect(pg_container)
        try:
            url = await conn.fetchval(
                "SELECT source_url FROM push_job_payloads WHERE job_id=$1::uuid", job_id
            )
        finally:
            await conn.close()
        assert url == "https://docs.example/foo?k=1"

    asyncio.run(_check())


def test_index_rejects_non_http_source_url(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_reidx_badurl")
    r = admin_client.post(
        "/api/v1/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "workspace": "ws_reidx_badurl",
            "path": "x.md",
            "content": "y",
            "source_url": "ftp://nope",
        },
    )
    assert r.status_code == 422
