from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_rerank_configs_columns(session_pool: asyncpg.Pool) -> None:
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS rerank_configs, indexer_configs, "
            "workspace_sources, index_jobs, indexed_documents, "
            "workspaces, schema_migrations CASCADE"
        )
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]: r["data_type"]
            for r in await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'rerank_configs'"
            )
        }
    expected = {
        "workspace_id", "provider", "model", "base_url", "api_key_ref",
        "top_k_pre_rerank", "created_at", "updated_at",
    }
    assert expected.issubset(cols.keys())
    assert cols["workspace_id"] == "uuid"
    assert cols["top_k_pre_rerank"] == "integer"


@pytest.mark.asyncio
async def test_rerank_configs_fk_cascade(session_pool: asyncpg.Pool) -> None:
    """Supprimer un workspace supprime sa rerank_config (ON DELETE CASCADE)."""
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS rerank_configs, indexer_configs, "
            "workspace_sources, index_jobs, indexed_documents, "
            "workspaces, schema_migrations CASCADE"
        )
    await run_migrations(session_pool, MIGRATIONS_DIR)

    dek = "x" * 32
    from hashlib import sha256
    api_key = "smoke"
    fp = sha256(api_key.encode()).hexdigest()
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ($1, pgp_sym_encrypt($2::text, $3::text)::bytea, $4, 'c', 'b') RETURNING id",
            "ws_cascade", api_key, dek, fp,
        )
        await conn.execute(
            "INSERT INTO rerank_configs (workspace_id, provider, model) "
            "VALUES ($1, 'cohere', 'rerank-v3.5')",
            ws_id,
        )
        await conn.execute("DELETE FROM workspaces WHERE id = $1", ws_id)
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM rerank_configs WHERE workspace_id = $1", ws_id,
        )
    assert count == 0


@pytest.mark.asyncio
async def test_rerank_configs_check_top_k_positive(session_pool: asyncpg.Pool) -> None:
    """CHECK contrainte top_k_pre_rerank > 0."""
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS rerank_configs, indexer_configs, "
            "workspace_sources, index_jobs, indexed_documents, "
            "workspaces, schema_migrations CASCADE"
        )
    await run_migrations(session_pool, MIGRATIONS_DIR)

    dek = "x" * 32
    from hashlib import sha256
    api_key = "smoke2"
    fp = sha256(api_key.encode()).hexdigest()
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ($1, pgp_sym_encrypt($2::text, $3::text)::bytea, $4, 'c', 'b') RETURNING id",
            "ws_check", api_key, dek, fp,
        )
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO rerank_configs (workspace_id, provider, model, top_k_pre_rerank) "
                "VALUES ($1, 'cohere', 'rerank-v3.5', 0)",
                ws_id,
            )
