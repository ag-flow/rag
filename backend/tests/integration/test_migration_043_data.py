from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_data_category_uses_data_strategy(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        strat = await conn.fetchval(
            "SELECT strategy_name FROM chunking_category_strategies "
            "WHERE category='data' AND workspace_id IS NULL"
        )
        algo = await conn.fetchval(
            "SELECT algo FROM chunking_strategies "
            "WHERE name='data-structured' AND workspace_id IS NULL"
        )
    assert strat == "data-structured"
    assert algo == "data"


@pytest.mark.asyncio
async def test_data_algo_allowed_by_check(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        # l'algo 'data' est désormais accepté par la contrainte CHECK
        await conn.execute(
            "INSERT INTO chunking_strategies (workspace_id, name, algo) "
            "VALUES (NULL, 'tmp-data', 'data')"
        )
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO chunking_strategies (workspace_id, name, algo) "
                "VALUES (NULL, 'tmp-bad', 'quantum')"
            )
