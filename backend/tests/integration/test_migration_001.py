from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_workspaces_columns(session_pool: asyncpg.Pool) -> None:
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS indexer_configs, workspaces, schema_migrations CASCADE"
        )
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
        "api_key_encrypted",
        "api_key_fingerprint",
        "rag_cnx",
        "rag_base",
        "sync_interval_seconds",
        "created_at",
        "updated_at",
    }
    assert expected.issubset(cols.keys())
    assert "api_key_hash" not in cols
    assert cols["sync_interval_seconds"] == "integer"


@pytest.mark.asyncio
async def test_workspaces_name_unique(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ('w_unique', pgp_sym_encrypt('k', 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'::text)::bytea, 'fp_w_unique_1', 'cnx1', 'base1')"
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
                "VALUES ('w_unique', pgp_sym_encrypt('k', 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'::text)::bytea, 'fp_w_unique_2', 'cnx2', 'base2')"
            )
        await conn.execute("DELETE FROM workspaces WHERE name = 'w_unique'")


@pytest.mark.asyncio
async def test_indexer_configs_cascade_on_workspace_delete(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ('w_cascade', pgp_sym_encrypt('k', 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'::text)::bytea, 'fp_w_cascade', 'c', 'b') RETURNING id"
        )
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
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ('w_unique_idx', pgp_sym_encrypt('k', 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'::text)::bytea, 'fp_w_unique_idx', 'c', 'b') RETURNING id"
        )
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
        await conn.execute("DELETE FROM workspaces WHERE id = $1", ws_id)
