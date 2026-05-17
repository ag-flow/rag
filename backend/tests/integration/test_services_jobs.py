from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import asyncpg
import pytest

from rag.api.errors import WorkspaceNotFound
from rag.db.migrations import run_migrations
from rag.schemas.admin import IndexerSpec, WorkspaceCreateRequest
from rag.services.jobs import create_pending_job, list_jobs
from rag.services.workspaces import create_workspace

_TEST_DEK = "x" * 32

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _Resolver:
    async def resolve_with_retry(self, ref: str) -> str:
        assert re.fullmatch(r"\$\{vault://[^:]+:[^}]+\}", ref)
        return "sk-x"


@pytest.fixture
def cleanup_ws_dbs(pg_container: str) -> Iterator[None]:
    yield
    import asyncio

    async def _cleanup() -> None:
        admin = await asyncpg.connect(pg_container.rsplit("/", 1)[0] + "/postgres")
        try:
            for r in await admin.fetch(
                "SELECT datname FROM pg_database WHERE datname LIKE 'rag_ws_%'"
            ):
                await admin.execute(f'DROP DATABASE IF EXISTS "{r["datname"]}" WITH (FORCE)')
        finally:
            await admin.close()

    asyncio.get_event_loop().run_until_complete(_cleanup())


@pytest.mark.asyncio
async def test_create_pending_job_inserts_row(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"

    await create_workspace(
        request=WorkspaceCreateRequest(
            name="ws_jobs",
            indexer=IndexerSpec(provider="openai", model="text-embedding-3-small", api_key_ref="k"),
        ),
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=_Resolver(),  # type: ignore[arg-type]
        default_vault_name="rag",
        api_key_dek=_TEST_DEK,
    )

    job = await create_pending_job(
        workspace_name="ws_jobs", triggered_by="manual", config_pool=session_pool
    )
    assert job["status"] == "pending"
    assert job["triggered_by"] == "manual"

    jobs = await list_jobs(session_pool, workspace_name="ws_jobs")
    assert len(jobs) == 1
    assert jobs[0]["id"] == job["id"]


@pytest.mark.asyncio
async def test_create_pending_job_workspace_not_found(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    with pytest.raises(WorkspaceNotFound):
        await create_pending_job(
            workspace_name="absent", triggered_by="manual", config_pool=session_pool
        )


@pytest.mark.asyncio
async def test_list_jobs_workspace_not_found(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    with pytest.raises(WorkspaceNotFound):
        await list_jobs(session_pool, workspace_name="absent")


@pytest.mark.asyncio
async def test_list_jobs_ordered_desc(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"

    await create_workspace(
        request=WorkspaceCreateRequest(
            name="ws_jobs_order",
            indexer=IndexerSpec(provider="openai", model="text-embedding-3-small", api_key_ref="k"),
        ),
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=_Resolver(),  # type: ignore[arg-type]
        default_vault_name="rag",
        api_key_dek=_TEST_DEK,
    )

    ws_id = await session_pool.fetchval("SELECT id FROM workspaces WHERE name='ws_jobs_order'")
    # Insert manuel pour forcer started_at en ordre désordonné
    async with session_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status, started_at) "
            "VALUES ($1, 'webhook', 'done', now() - interval '1 hour')",
            ws_id,
        )
        await conn.execute(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status, started_at) "
            "VALUES ($1, 'manual', 'done', now())",
            ws_id,
        )

    jobs = await list_jobs(session_pool, workspace_name="ws_jobs_order")
    assert len(jobs) == 2
    assert jobs[0]["triggered_by"] == "manual"  # plus récent en premier
