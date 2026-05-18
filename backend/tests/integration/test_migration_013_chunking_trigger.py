from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def _reset(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS chunking_configs, rerank_configs, indexer_configs, "
            "workspace_sources, index_jobs, indexed_documents, "
            "workspaces, harpocrate_vaults, model_dimensions, "
            "schema_migrations CASCADE"
        )


@pytest.mark.asyncio
async def test_triggered_by_accepts_reindex_chunking_change(
    session_pool: asyncpg.Pool,
) -> None:
    """Migration 013 élargit le CHECK pour accepter 'reindex_chunking_change'."""
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_chunk_trig")
        await conn.execute(
            "INSERT INTO index_jobs (workspace_id, triggered_by) VALUES ($1, $2)",
            ws_id,
            "reindex_chunking_change",
        )
        rows = await conn.fetch(
            "SELECT triggered_by FROM index_jobs WHERE workspace_id = $1",
            ws_id,
        )
    assert rows[0]["triggered_by"] == "reindex_chunking_change"


@pytest.mark.asyncio
async def test_triggered_by_rejects_unknown(session_pool: asyncpg.Pool) -> None:
    """Les valeurs hors enum restent rejetées par la CHECK constraint."""
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_chunk_trig_bad")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO index_jobs (workspace_id, triggered_by) VALUES ($1, $2)",
                ws_id,
                "nope",
            )


@pytest.mark.asyncio
async def test_triggered_by_still_accepts_reindex_indexer_change(
    session_pool: asyncpg.Pool,
) -> None:
    """La 013 ne casse pas la valeur ajoutée par la 007."""
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_chunk_trig_indexer")
        await conn.execute(
            "INSERT INTO index_jobs (workspace_id, triggered_by) VALUES ($1, $2)",
            ws_id,
            "reindex_indexer_change",
        )
        val = await conn.fetchval(
            "SELECT triggered_by FROM index_jobs WHERE workspace_id = $1",
            ws_id,
        )
    assert val == "reindex_indexer_change"
