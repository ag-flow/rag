from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_engine_flag_added_default_legacy(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_engine")
        await conn.execute(
            "INSERT INTO chunking_configs "
            "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
            "VALUES ($1, 'paragraph', 2000, 200, 200)",
            ws_id,
        )
        engine = await conn.fetchval(
            "SELECT engine FROM chunking_configs WHERE workspace_id=$1", ws_id
        )
    assert engine == "legacy"


@pytest.mark.asyncio
async def test_engine_check_rejects_unknown(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_engine_bad")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO chunking_configs "
                "(workspace_id, strategy, max_chars, min_chars, overlap_chars, engine) "
                "VALUES ($1, 'paragraph', 2000, 200, 200, 'turbo')",
                ws_id,
            )


@pytest.mark.asyncio
async def test_global_seeds_present(session_pool: asyncpg.Pool) -> None:
    """État des seeds à HEAD : 040 + 042 (code-aware→code) + 043 (data) + 057
    (name → label/slug, seeds devenus stratégies système)."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        strategies = {
            r["slug"]: r["algo"]
            for r in await conn.fetch(
                "SELECT slug, algo FROM chunking_strategies "
                "WHERE workspace_id IS NULL AND owner_id IS NULL"
            )
        }
        cat_strat = {
            r["category"]: r["strategy_name"]
            for r in await conn.fetch(
                "SELECT category, strategy_name FROM chunking_category_strategies "
                "WHERE workspace_id IS NULL"
            )
        }
        md_cat = await conn.fetchval(
            "SELECT category FROM chunking_extension_categories "
            "WHERE workspace_id IS NULL AND extension='.md'"
        )
        py_cat = await conn.fetchval(
            "SELECT category FROM chunking_extension_categories "
            "WHERE workspace_id IS NULL AND extension='.py'"
        )
        csv_cat = await conn.fetchval(
            "SELECT category FROM chunking_extension_categories "
            "WHERE workspace_id IS NULL AND extension='.csv'"
        )
    assert strategies == {
        "markdown-deep": "prose",
        "code-aware": "code",
        "table": "table",
        "data-structured": "data",
    }
    assert cat_strat == {
        "prose": "markdown-deep",
        "code": "code-aware",
        "table": "table",
        "data": "data-structured",
    }
    assert (md_cat, py_cat, csv_cat) == ("prose", "code", "table")


@pytest.mark.asyncio
async def test_system_strategy_slug_unique(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO chunking_strategies (workspace_id, label, slug, algo) "
                "VALUES (NULL, 'markdown-deep', 'markdown-deep', 'prose')"
            )


@pytest.mark.asyncio
async def test_workspace_can_shadow_global_strategy_slug(session_pool: asyncpg.Pool) -> None:
    """Un workspace peut définir une stratégie 'markdown-deep' propre sans
    collision avec le système (index uniques partiels distincts)."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_shadow")
        await conn.execute(
            "INSERT INTO chunking_strategies (workspace_id, label, slug, algo, params) "
            "VALUES ($1, 'markdown-deep', 'markdown-deep', 'prose', '{}'::jsonb)",
            ws_id,
        )
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM chunking_strategies WHERE slug='markdown-deep'"
        )
    assert count == 2  # système + workspace


@pytest.mark.asyncio
async def test_workspace_routing_cascade_on_delete(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_cascade_routing")
        await conn.execute(
            "INSERT INTO chunking_extension_categories (workspace_id, extension, category) "
            "VALUES ($1, '.md', 'table')",
            ws_id,
        )
        await conn.execute("DELETE FROM workspaces WHERE id=$1", ws_id)
        remaining = await conn.fetchval(
            "SELECT COUNT(*) FROM chunking_extension_categories WHERE workspace_id=$1",
            ws_id,
        )
    assert remaining == 0
