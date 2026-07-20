from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_owner_id_column_nullable_default_shared(session_pool: asyncpg.Pool) -> None:
    """068 : colonne owner_id présente, nullable ; INSERT sans owner → NULL (partagé)."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_068_shared", rag_base="rag_068s")
        owner = await conn.fetchval("SELECT owner_id FROM workspaces WHERE id = $1", ws_id)
        assert owner is None

        owned = await seed_workspace(
            conn, name="ws_068_owned", rag_base="rag_068o", owner_id="x" * 64
        )
        owner2 = await conn.fetchval("SELECT owner_id FROM workspaces WHERE id = $1", owned)
        assert owner2 == "x" * 64
