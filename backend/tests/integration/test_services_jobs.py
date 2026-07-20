from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncpg
import pytest

from rag.api.errors import JobNotFound, WorkspaceNotFound
from rag.db.migrations import run_migrations
from rag.schemas.admin import IndexerCreateSpec, WorkspaceCreateResolved
from rag.schemas.harpocrate_vaults import VaultSummary
from rag.services.jobs import create_pending_job, list_job_files, list_jobs
from rag.services.workspaces import create_workspace
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _Resolver:
    async def resolve_with_retry(self, ref: str) -> str:
        return "sk-x"


def _make_harpo_service() -> MagicMock:
    """Stub HarpocrateVaultsService : get_default (await par create_workspace)
    doit être un AsyncMock."""
    service = MagicMock()
    vault = MagicMock(spec=VaultSummary)
    vault.id = uuid4()
    vault.name = "rag"
    service.get_by_name = AsyncMock(return_value=vault)
    service.get_default = AsyncMock(return_value=vault)
    return service


def _make_request(name: str) -> WorkspaceCreateResolved:
    return WorkspaceCreateResolved(
        name=name,
        label=name,
        indexer=IndexerCreateSpec(
            provider="openai", model="text-embedding-3-small", api_key_ref="k"
        ),
    )


@pytest.fixture
def cleanup_ws_dbs(pg_container: str) -> Iterator[None]:
    yield

    async def _cleanup() -> None:
        admin = await asyncpg.connect(pg_container.rsplit("/", 1)[0] + "/postgres")
        try:
            for r in await admin.fetch(
                "SELECT datname FROM pg_database WHERE datname LIKE 'rag_ws_%'"
            ):
                await admin.execute(f'DROP DATABASE IF EXISTS "{r["datname"]}" WITH (FORCE)')
        finally:
            await admin.close()

    asyncio.run(_cleanup())


@pytest.mark.asyncio
async def test_create_pending_job_inserts_row(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"

    await create_workspace(
        request=_make_request("ws_jobs"),
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=_Resolver(),  # type: ignore[arg-type]
        harpocrate_vaults_service=_make_harpo_service(),
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
        request=_make_request("ws_jobs_order"),
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=_Resolver(),  # type: ignore[arg-type]
        harpocrate_vaults_service=_make_harpo_service(),
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


@pytest.mark.asyncio
async def test_list_job_files_returns_files(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_jf")
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status) "
            "VALUES ($1, 'manual', 'done') RETURNING id",
            ws_id,
        )
        await conn.execute(
            "INSERT INTO index_job_files (job_id, path, change_type) "
            "VALUES ($1, 'b.md', 'modified'), ($1, 'a.md', 'added')",
            job_id,
        )

    result = await list_job_files(
        config_pool=session_pool, workspace_name="ws_jf", job_id=str(job_id)
    )
    assert result["total"] == 2
    assert result["limit"] == 1000
    assert {(f["path"], f["change_type"]) for f in result["files"]} == {
        ("a.md", "added"),
        ("b.md", "modified"),
    }


@pytest.mark.asyncio
async def test_list_job_files_unknown_job_raises(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await seed_workspace(conn, name="ws_jf2")

    with pytest.raises(JobNotFound):
        await list_job_files(config_pool=session_pool, workspace_name="ws_jf2", job_id=str(uuid4()))
