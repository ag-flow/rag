from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.fixture
async def pool(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM workspaces")
    return session_pool


@pytest.mark.asyncio
async def test_retry_count_column_exists_with_default(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="mig046_a")
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status) "
            "VALUES ($1, 'push', 'pending') RETURNING id",
            ws_id,
        )
        row = await conn.fetchrow(
            "SELECT retry_count, retry_after FROM index_jobs WHERE id=$1", job_id
        )
        assert row["retry_count"] == 0
        assert row["retry_after"] is None


@pytest.mark.asyncio
async def test_circuit_breaker_table_created(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="mig046_b")
        await conn.execute(
            "INSERT INTO indexer_circuit_breakers"
            " (workspace_id, provider, model, error_message)"
            " VALUES ($1, 'openai', 'text-embedding-3-small', 'err')",
            ws_id,
        )
        row = await conn.fetchrow(
            "SELECT provider, model, open_until FROM indexer_circuit_breakers"
            " WHERE workspace_id=$1",
            ws_id,
        )
        assert row["provider"] == "openai"
        assert row["model"] == "text-embedding-3-small"
        assert row["open_until"] is None


@pytest.mark.asyncio
async def test_circuit_breaker_unique_per_workspace(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="mig046_c")
        await conn.execute(
            "INSERT INTO indexer_circuit_breakers"
            " (workspace_id, provider, model, error_message)"
            " VALUES ($1, 'openai', 'text-embedding-3-small', 'err')",
            ws_id,
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO indexer_circuit_breakers"
                " (workspace_id, provider, model, error_message)"
                " VALUES ($1, 'openai', 'text-embedding-3-large', 'err2')",
                ws_id,
            )


@pytest.mark.asyncio
async def test_circuit_breaker_cascade_delete(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="mig046_d")
        await conn.execute(
            "INSERT INTO indexer_circuit_breakers"
            " (workspace_id, provider, model, error_message)"
            " VALUES ($1, 'openai', 'text-embedding-3-small', 'err')",
            ws_id,
        )
        await conn.execute("DELETE FROM workspaces WHERE id=$1", ws_id)
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM indexer_circuit_breakers WHERE workspace_id=$1",
            ws_id,
        )
        assert count == 0
