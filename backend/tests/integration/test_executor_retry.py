from __future__ import annotations

from pathlib import Path
from uuid import UUID

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.indexer.providers.protocol import EmbeddingRateLimited
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


class _FailingIndexer:
    """Indexer qui lève une erreur configurable."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def index_file(self, **_: object) -> int:
        raise self._exc

    async def delete_file(self, **_: object) -> None:
        raise self._exc


@pytest.fixture
async def pool(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM workspaces")
    return session_pool


async def _seed_push_job(pool: asyncpg.Pool, ws_name: str) -> tuple[str, UUID]:
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name=ws_name)
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status, correlation_id) "
            "VALUES ($1, 'push', 'pending', 'corr-retry-001') RETURNING id",
            ws_id,
        )
        await conn.execute(
            "INSERT INTO push_job_payloads (job_id, path, content) VALUES ($1, $2, $3)",
            job_id,
            "doc.md",
            "hello",
        )
    return str(job_id), ws_id


@pytest.mark.asyncio
async def test_transient_error_reschedules_job(
    pool: asyncpg.Pool, tmp_path: Path
) -> None:
    job_id, _ = await _seed_push_job(pool, "ws_retry1")
    indexer = _FailingIndexer(EmbeddingRateLimited("rate limited"))

    result = await execute_next_pending_job(
        config_pool=pool,
        storage=RepoStorage(tmp_path),
        indexer=indexer,  # type: ignore[arg-type]
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
        webhook_secret=None,
    )
    assert result is True

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, retry_count, retry_after FROM index_jobs WHERE id=$1::uuid",
            job_id,
        )
        assert row["status"] == "pending"
        assert row["retry_count"] == 1
        assert row["retry_after"] is not None

        # payload conservé pour le retry
        payload = await conn.fetchval(
            "SELECT job_id FROM push_job_payloads WHERE job_id=$1::uuid", job_id
        )
        assert payload is not None


@pytest.mark.asyncio
async def test_transient_error_becomes_error_after_max_retries(
    pool: asyncpg.Pool, tmp_path: Path
) -> None:
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_retry2")
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        # Job déjà à retry_count=3 (MAX_RETRIES atteint)
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs"
            " (workspace_id, triggered_by, status, correlation_id, retry_count)"
            " VALUES ($1, 'push', 'pending', 'corr-retry-002', 3) RETURNING id",
            ws_id,
        )
        await conn.execute(
            "INSERT INTO push_job_payloads (job_id, path, content) VALUES ($1, $2, $3)",
            job_id,
            "doc.md",
            "hello",
        )

    indexer = _FailingIndexer(EmbeddingRateLimited("still rate limited"))
    await execute_next_pending_job(
        config_pool=pool,
        storage=RepoStorage(tmp_path),
        indexer=indexer,  # type: ignore[arg-type]
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
        webhook_secret=None,
    )

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status FROM index_jobs WHERE id=$1", job_id
        )
        assert row["status"] == "error"
