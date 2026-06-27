from __future__ import annotations

from pathlib import Path
from uuid import UUID

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.indexer.providers.protocol import EmbeddingAuthError, EmbeddingQuotaExhausted
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


async def _seed_delete_job(
    pool: asyncpg.Pool, ws_name: str, path: str = "doc.md"
) -> tuple[str, UUID]:
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name=ws_name)
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension)"
            " VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status, correlation_id)"
            " VALUES ($1, 'delete', 'pending', 'corr-del-cb') RETURNING id",
            ws_id,
        )
        await conn.execute(
            "INSERT INTO delete_job_payloads (job_id, path) VALUES ($1, $2)",
            job_id,
            path,
        )
    return str(job_id), ws_id


@pytest.mark.asyncio
async def test_delete_job_quota_error_opens_circuit(
    pool: asyncpg.Pool, tmp_path: Path
) -> None:
    job_id, ws_id = await _seed_delete_job(pool, "ws_del_cb_quota")
    indexer = _FailingIndexer(EmbeddingQuotaExhausted("no credits"))

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
            "SELECT status FROM index_jobs WHERE id=$1::uuid", job_id
        )
        assert row["status"] == "error"

        circuit = await conn.fetchrow(
            "SELECT provider, model FROM indexer_circuit_breakers"
            " WHERE workspace_id=$1",
            ws_id,
        )
        assert circuit is not None
        assert circuit["provider"] == "openai"


@pytest.mark.asyncio
async def test_delete_job_auth_error_opens_circuit(
    pool: asyncpg.Pool, tmp_path: Path
) -> None:
    _, ws_id = await _seed_delete_job(pool, "ws_del_cb_auth")
    indexer = _FailingIndexer(EmbeddingAuthError("invalid key"))

    await execute_next_pending_job(
        config_pool=pool,
        storage=RepoStorage(tmp_path),
        indexer=indexer,  # type: ignore[arg-type]
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
        webhook_secret=None,
    )

    async with pool.acquire() as conn:
        circuit = await conn.fetchrow(
            "SELECT 1 FROM indexer_circuit_breakers WHERE workspace_id=$1",
            ws_id,
        )
        assert circuit is not None


@pytest.mark.asyncio
async def test_delete_job_circuit_open_skips_job(
    pool: asyncpg.Pool, tmp_path: Path
) -> None:
    """Un delete job dont le workspace a un circuit ouvert n'est pas execute."""
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_del_cb_skip")
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension)"
            " VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status)"
            " VALUES ($1, 'delete', 'pending') RETURNING id",
            ws_id,
        )
        await conn.execute(
            "INSERT INTO delete_job_payloads (job_id, path) VALUES ($1, 'doc.md')",
            job_id,
        )
        await conn.execute(
            "INSERT INTO indexer_circuit_breakers"
            " (workspace_id, provider, model, error_message, open_until)"
            " VALUES ($1, 'openai', 'text-embedding-3-small', 'err',"
            " now() + interval '1 hour')",
            ws_id,
        )

    result = await execute_next_pending_job(
        config_pool=pool,
        storage=RepoStorage(tmp_path),
        indexer=_FailingIndexer(RuntimeError("must not be called")),  # type: ignore[arg-type]
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
        webhook_secret=None,
    )
    assert result is False

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status FROM index_jobs WHERE id=$1", job_id
        )
        assert row["status"] == "pending"
