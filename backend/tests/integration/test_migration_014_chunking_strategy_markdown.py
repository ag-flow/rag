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
async def test_chunking_configs_accepts_markdown_strategy(
    session_pool: asyncpg.Pool,
) -> None:
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_md_strategy")
        await conn.execute(
            "INSERT INTO chunking_configs "
            "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
            "VALUES ($1, 'markdown', 2000, 200, 200)",
            ws_id,
        )
        row = await conn.fetchrow(
            "SELECT strategy FROM chunking_configs WHERE workspace_id = $1",
            ws_id,
        )
    assert row is not None
    assert row["strategy"] == "markdown"


@pytest.mark.asyncio
async def test_chunking_configs_still_accepts_paragraph(
    session_pool: asyncpg.Pool,
) -> None:
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_md_para")
        await conn.execute(
            "INSERT INTO chunking_configs "
            "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
            "VALUES ($1, 'paragraph', 2000, 200, 200)",
            ws_id,
        )
        row = await conn.fetchrow(
            "SELECT strategy FROM chunking_configs WHERE workspace_id = $1",
            ws_id,
        )
    assert row is not None
    assert row["strategy"] == "paragraph"


@pytest.mark.asyncio
async def test_chunking_configs_rejects_unknown_strategy(
    session_pool: asyncpg.Pool,
) -> None:
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_md_bad")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO chunking_configs "
                "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
                "VALUES ($1, 'unknown_strategy', 2000, 200, 200)",
                ws_id,
            )
