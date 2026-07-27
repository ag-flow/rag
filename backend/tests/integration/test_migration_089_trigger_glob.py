from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_pattern_replaces_extension(session_pool: asyncpg.Pool) -> None:
    """Migration 089 : la colonne `pattern` (glob) remplace `extension`."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        columns = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'workspace_extension_triggers'"
            )
        }
    assert "pattern" in columns
    assert "extension" not in columns


@pytest.mark.asyncio
async def test_pattern_unique_per_workspace(session_pool: asyncpg.Pool) -> None:
    """Unicité (workspace_id, pattern) — même garde que l'ancienne extension."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_glob_089")
        await conn.execute(
            "INSERT INTO workspace_extension_triggers (workspace_id, pattern) "
            "VALUES ($1, 'backlog/**/*.md')",
            ws_id,
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO workspace_extension_triggers (workspace_id, pattern) "
                "VALUES ($1, 'backlog/**/*.md')",
                ws_id,
            )
