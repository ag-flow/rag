from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

OWNER = "5" * 64


async def _seed_strategy(conn: asyncpg.Connection, slug: str) -> object:
    return await conn.fetchval(
        "INSERT INTO chunking_strategies (owner_id, label, slug, algo) "
        "VALUES ($1, $2, $2, 'prose') RETURNING id",
        OWNER,
        slug,
    )


@pytest.mark.asyncio
async def test_bindings_columns_with_restrict(session_pool: asyncpg.Pool) -> None:
    """Les deux bindings durables existent et protègent la stratégie liée
    (ON DELETE RESTRICT — contrairement au payload transient de 059)."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_bindings_060")
        await conn.execute(
            "INSERT INTO chunking_configs "
            "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
            "VALUES ($1, 'paragraph', 2000, 200, 200)",
            ws_id,
        )
        default_sid = await _seed_strategy(conn, "binding-defaut")
        trigger_sid = await _seed_strategy(conn, "binding-trigger")

        await conn.execute(
            "UPDATE chunking_configs SET default_strategy_id=$1 WHERE workspace_id=$2",
            default_sid,
            ws_id,
        )
        await conn.execute(
            "INSERT INTO workspace_extension_triggers "
            "(workspace_id, pattern, enabled, strategy_id) VALUES ($1, '**/*.md', true, $2)",
            ws_id,
            trigger_sid,
        )

        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await conn.execute("DELETE FROM chunking_strategies WHERE id=$1", default_sid)
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await conn.execute("DELETE FROM chunking_strategies WHERE id=$1", trigger_sid)

        # Détacher les bindings libère la suppression.
        await conn.execute(
            "UPDATE chunking_configs SET default_strategy_id=NULL WHERE workspace_id=$1", ws_id
        )
        await conn.execute(
            "UPDATE workspace_extension_triggers SET strategy_id=NULL WHERE workspace_id=$1",
            ws_id,
        )
        await conn.execute("DELETE FROM chunking_strategies WHERE id=$1", default_sid)
        await conn.execute("DELETE FROM chunking_strategies WHERE id=$1", trigger_sid)
