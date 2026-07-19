from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_new_chunking_config_defaults_to_structured(session_pool: asyncpg.Pool) -> None:
    """065 : un INSERT sans colonne engine prend 'structured' (nouveaux workspaces)."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(
            conn, name="ws_engine_default", rag_cnx="postgresql://test/e", rag_base="e"
        )
        await conn.execute(
            "INSERT INTO chunking_configs "
            "(workspace_id, strategy, max_chars, min_chars, overlap_chars, extras) "
            "VALUES ($1, 'paragraph', 2000, 200, 200, '{}'::jsonb)",
            ws_id,
        )
        engine = await conn.fetchval(
            "SELECT engine FROM chunking_configs WHERE workspace_id = $1", ws_id
        )
    assert engine == "structured"
