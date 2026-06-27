from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_code_aware_uses_code_algo(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        algo = await conn.fetchval(
            "SELECT algo FROM chunking_strategies "
            "WHERE name='code-aware' AND workspace_id IS NULL"
        )
        # le couple catégorie->stratégie reste inchangé
        code_strategy = await conn.fetchval(
            "SELECT strategy_name FROM chunking_category_strategies "
            "WHERE category='code' AND workspace_id IS NULL"
        )
    assert algo == "code"
    assert code_strategy == "code-aware"
