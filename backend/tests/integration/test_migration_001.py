from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_workspaces_columns(session_pool: asyncpg.Pool) -> None:
    """État FINAL du schéma workspaces à HEAD : les colonnes api_key_* ont
    toutes disparu au fil des migrations (010, 015, 033)."""
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]: r["data_type"]
            for r in await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'workspaces'"
            )
        }
    expected = {
        "id",
        "name",
        "rag_cnx",
        "rag_base",
        "sync_interval_seconds",
        "allow_full_read",
        "created_at",
        "updated_at",
    }
    assert expected.issubset(cols.keys())
    assert "api_key_hash" not in cols
    assert "api_key_encrypted" not in cols
    assert "api_key_ref" not in cols
    assert "api_key_fingerprint" not in cols
    assert cols["sync_interval_seconds"] == "integer"


@pytest.mark.asyncio
async def test_workspaces_name_unique(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await seed_workspace(conn, name="w_unique")
        with pytest.raises(asyncpg.UniqueViolationError):
            await seed_workspace(conn, name="w_unique")


@pytest.mark.asyncio
async def test_indexer_configs_cascade_on_workspace_delete(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="w_cascade")
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        before = await conn.fetchval(
            "SELECT COUNT(*) FROM indexer_configs WHERE workspace_id = $1", ws_id
        )
        assert before == 1

        await conn.execute("DELETE FROM workspaces WHERE id = $1", ws_id)
        after = await conn.fetchval(
            "SELECT COUNT(*) FROM indexer_configs WHERE workspace_id = $1", ws_id
        )
        assert after == 0


@pytest.mark.asyncio
async def test_indexer_configs_unique_per_workspace(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="w_unique_idx")
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
                "VALUES ($1, 'openai', 'text-embedding-3-large', 3072)",
                ws_id,
            )
