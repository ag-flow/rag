from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_push_payloads_carry_strategy_id_not_override(
    session_pool: asyncpg.Pool,
) -> None:
    """Le payload push lie une stratégie PAR ID (spec chunking §5) — la
    colonne slug `strategy_override` a disparu, sans FK (le job échoue avec
    une erreur typée si l'id ne résout plus, jamais de repli silencieux)."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        columns = {
            r["column_name"]: r["data_type"]
            for r in await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'push_job_payloads'"
            )
        }
        fk_count = await conn.fetchval(
            "SELECT count(*) FROM information_schema.table_constraints "
            "WHERE table_name = 'push_job_payloads' AND constraint_type = 'FOREIGN KEY' "
            "AND constraint_name LIKE '%strategy%'"
        )
    assert "strategy_override" not in columns
    assert columns.get("strategy_id") == "uuid"
    assert fk_count == 0
