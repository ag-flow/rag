from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_search_config_columns_and_checks(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_search_cfg_063")
        await conn.execute("INSERT INTO hybrid_configs (workspace_id) VALUES ($1)", ws_id)
        row = await conn.fetchrow(
            "SELECT weight_lexical, weight_vector, lexical_engine FROM hybrid_configs "
            "WHERE workspace_id=$1",
            ws_id,
        )
        assert (row["weight_lexical"], row["weight_vector"], row["lexical_engine"]) == (
            0.5,
            0.5,
            "fts",
        )
        cols = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='hybrid_configs'"
            )
        }
        assert "fts_config" not in cols
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "UPDATE hybrid_configs SET lexical_engine='elastic' WHERE workspace_id=$1",
                ws_id,
            )
        # nouveau type de job accepté
        await conn.execute(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status) "
            "VALUES ($1, 'rebuild_lexical_index', 'pending')",
            ws_id,
        )
