from __future__ import annotations

from pathlib import Path
from uuid import UUID

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.indexer.noop import NoOpIndexer
from rag.sync.executor import execute_next_pending_job
from rag.sync.repo_storage import RepoStorage
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _StubResolver:
    async def resolve_with_retry(self, ref: str) -> str:
        return "tok"


class _StubClientProvider:
    async def get_default_vault_name(self) -> str | None:
        return "rag"


@pytest.fixture
async def pool(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM workspaces")
    return session_pool


async def _seed_delete_job(
    pool: asyncpg.Pool, ws_name: str, path: str
) -> tuple[str, UUID]:
    """Seed workspace + delete job. Returns (job_id, workspace_id)."""
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name=ws_name)
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status, correlation_id) "
            "VALUES ($1, 'delete', 'pending', 'corr-del-001') RETURNING id",
            ws_id,
        )
        await conn.execute(
            "INSERT INTO delete_job_payloads (job_id, path) VALUES ($1, $2)",
            job_id,
            path,
        )
    return str(job_id), ws_id


@pytest.mark.asyncio
async def test_delete_job_done_when_document_exists(
    pool: asyncpg.Pool, tmp_path: Path
) -> None:
    storage = RepoStorage(tmp_path)
    indexer = NoOpIndexer(pool)
    path = "docs/guide.md"

    job_id, ws_id = await _seed_delete_job(pool, "ws_del1", path)

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
            "VALUES ($1, $2, 'sha256:abc', 'openai/text-embedding-3-small')",
            ws_id,
            path,
        )

    result = await execute_next_pending_job(
        config_pool=pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
        webhook_secret=None,
    )
    assert result is True

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, files_changed FROM index_jobs WHERE id=$1::uuid", job_id
        )
        assert row["status"] == "done"
        assert row["files_changed"] == 1

        payload = await conn.fetchval(
            "SELECT job_id FROM delete_job_payloads WHERE job_id=$1::uuid", job_id
        )
        assert payload is None  # cleaned up

        doc = await conn.fetchval(
            "SELECT 1 FROM indexed_documents WHERE workspace_id=$1 AND path=$2",
            ws_id,
            path,
        )
        assert doc is None  # supprimé


@pytest.mark.asyncio
async def test_delete_job_skipped_when_document_absent(
    pool: asyncpg.Pool, tmp_path: Path
) -> None:
    storage = RepoStorage(tmp_path)
    indexer = NoOpIndexer(pool)

    job_id, _ = await _seed_delete_job(pool, "ws_del2", "missing.md")

    result = await execute_next_pending_job(
        config_pool=pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
        webhook_secret=None,
    )
    assert result is True

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status FROM index_jobs WHERE id=$1::uuid", job_id
        )
        assert row["status"] == "skipped"
