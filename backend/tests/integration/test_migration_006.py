from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_idx_jobs_workspace_started_index_exists(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        indexname = await conn.fetchval(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'index_jobs' AND indexname = 'idx_jobs_workspace_started'"
        )
    assert indexname == "idx_jobs_workspace_started"
