from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_rerank_configs_columns(session_pool: asyncpg.Pool) -> None:
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
        "workspace_id",
        "provider",
        "model",
        "base_url",
        "api_key_ref",
        "top_k_pre_rerank",
        "created_at",
        "updated_at",
    }
    assert expected.issubset(cols.keys())
    assert cols["workspace_id"] == "uuid"
    assert cols["top_k_pre_rerank"] == "integer"


@pytest.mark.asyncio
async def test_rerank_configs_fk_cascade(session_pool: asyncpg.Pool) -> None:
    """Supprimer un workspace supprime sa rerank_config (ON DELETE CASCADE)."""
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_cascade")
        await conn.execute(
            "INSERT INTO rerank_configs (workspace_id, provider, model) "
            "VALUES ($1, 'cohere', 'rerank-v3.5')",
            ws_id,
        )
        await conn.execute("DELETE FROM workspaces WHERE id = $1", ws_id)
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM rerank_configs WHERE workspace_id = $1",
            ws_id,
        )
    assert count == 0


@pytest.mark.asyncio
async def test_rerank_configs_check_top_k_positive(session_pool: asyncpg.Pool) -> None:
    """CHECK contrainte top_k_pre_rerank > 0."""
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_check")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO rerank_configs (workspace_id, provider, model, top_k_pre_rerank) "
                "VALUES ($1, 'cohere', 'rerank-v3.5', 0)",
                ws_id,
            )
