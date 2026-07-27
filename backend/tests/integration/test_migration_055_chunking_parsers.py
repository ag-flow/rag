from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_chunking_parsers_seeded_with_markdown(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        rows = await conn.fetch("SELECT slug, label FROM chunking_parsers ORDER BY slug")
    assert [(r["slug"], r["label"]) for r in rows] == [("markdown", "Markdown")]


@pytest.mark.asyncio
async def test_chunking_parsers_slug_is_primary_key(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO chunking_parsers (slug, label) VALUES ('markdown', 'Doublon')"
            )
