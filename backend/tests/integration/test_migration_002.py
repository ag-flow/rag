from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_workspace_sources_columns(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]: r["data_type"]
            for r in await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'workspace_sources'"
            )
        }
    expected = {
        "id",
        "workspace_id",
        "type",
        "config",
        "last_indexed_at",
        "next_sync_at",
        "created_at",
    }
    assert expected.issubset(cols.keys())
    assert cols["config"] == "jsonb"


@pytest.mark.asyncio
async def test_workspace_sources_default_type_git(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ('w_mig002', pgp_sym_encrypt('k', 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'::text)::bytea, 'fp_w_mig002', 'c', 'b') RETURNING id"
        )
        src_id = await conn.fetchval(
            "INSERT INTO workspace_sources (workspace_id, config) "
            'VALUES ($1, \'{"url":"https://x"}\'::jsonb) RETURNING id',
            ws_id,
        )
        typ = await conn.fetchval("SELECT type FROM workspace_sources WHERE id = $1", src_id)
        assert typ == "git"
        await conn.execute("DELETE FROM workspaces WHERE id = $1", ws_id)


@pytest.mark.asyncio
async def test_workspace_sources_next_sync_index(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        idx = await conn.fetchval(
            "SELECT indexname FROM pg_indexes WHERE indexname = 'idx_sources_next_sync'"
        )
        assert idx == "idx_sources_next_sync"


@pytest.mark.asyncio
async def test_workspace_sources_cascade_on_workspace_delete(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ('w_mig002_casc', pgp_sym_encrypt('k', 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'::text)::bytea, 'fp_w_mig002_casc', 'c', 'b') RETURNING id"
        )
        await conn.execute(
            "INSERT INTO workspace_sources (workspace_id, config) VALUES ($1, '{}'::jsonb)",
            ws_id,
        )
        before = await conn.fetchval(
            "SELECT COUNT(*) FROM workspace_sources WHERE workspace_id = $1", ws_id
        )
        assert before == 1

        await conn.execute("DELETE FROM workspaces WHERE id = $1", ws_id)
        after = await conn.fetchval(
            "SELECT COUNT(*) FROM workspace_sources WHERE workspace_id = $1", ws_id
        )
        assert after == 0
