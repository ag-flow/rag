from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

OWNER_A = "a" * 64
OWNER_B = "b" * 64


@pytest.mark.asyncio
async def test_seeds_migrated_to_system_strategies(session_pool: asyncpg.Pool) -> None:
    """Les seeds deviennent des stratégies système : owner NULL, label=slug=ancien
    name, parser_slug NULL, et la colonne `name` a disparu."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT label, slug, owner_id, parser_slug FROM chunking_strategies "
            "WHERE workspace_id IS NULL AND owner_id IS NULL"
        )
        columns = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'chunking_strategies'"
            )
        }
    slugs = {r["slug"] for r in rows}
    assert {"markdown-deep", "code-aware", "table", "data-structured"} <= slugs
    assert all(r["label"] == r["slug"] for r in rows)
    assert all(r["parser_slug"] is None for r in rows)
    assert "name" not in columns
    assert {"owner_id", "label", "slug", "parser_slug"} <= columns


@pytest.mark.asyncio
async def test_owner_slug_unique_per_owner_only(session_pool: asyncpg.Pool) -> None:
    """Même slug autorisé chez deux owners différents (et vs système), refusé
    en double chez le même owner."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO chunking_strategies (owner_id, label, slug, algo) "
            "VALUES ($1, 'Ma prose', 'ma-prose', 'prose'), "
            "($2, 'Ma prose', 'ma-prose', 'prose'), "
            "($1, 'markdown-deep', 'markdown-deep', 'prose')",
            OWNER_A,
            OWNER_B,
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO chunking_strategies (owner_id, label, slug, algo) "
                "VALUES ($1, 'Ma prose bis', 'ma-prose', 'prose')",
                OWNER_A,
            )


@pytest.mark.asyncio
async def test_parser_slug_fk(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO chunking_strategies (owner_id, label, slug, algo, parser_slug) "
            "VALUES ($1, 'Avec régions', 'avec-regions', 'prose', 'markdown')",
            OWNER_A,
        )
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await conn.execute(
                "INSERT INTO chunking_strategies (owner_id, label, slug, algo, parser_slug) "
                "VALUES ($1, 'Parser fantôme', 'parser-fantome', 'prose', 'pdf')",
                OWNER_A,
            )


@pytest.mark.asyncio
async def test_owner_xor_workspace_check(session_pool: asyncpg.Pool) -> None:
    """Une stratégie ne peut pas être à la fois possédée et override workspace."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_owner_xor")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO chunking_strategies (workspace_id, owner_id, label, slug, algo) "
                "VALUES ($1, $2, 'Hybride', 'hybride', 'prose')",
                ws_id,
                OWNER_A,
            )
