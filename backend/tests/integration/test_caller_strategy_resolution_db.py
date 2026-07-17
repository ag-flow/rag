from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.services.chunking_routing import (
    UnknownStrategySlugError,
    resolve_caller_strategy,
)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

OWNER_A = "3" * 64
OWNER_B = "4" * 64


async def _seed(conn: asyncpg.Connection, owner_id: str | None, slug: str) -> None:
    await conn.execute(
        "INSERT INTO chunking_strategies (owner_id, label, slug, algo) "
        "VALUES ($1, $2, $2, 'prose') ON CONFLICT DO NOTHING",
        owner_id,
        slug,
    )


@pytest.mark.asyncio
async def test_caller_library_shadows_system_slug(session_pool: asyncpg.Pool) -> None:
    from rag.db.migrations import run_migrations

    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await _seed(conn, OWNER_A, "markdown-deep")  # même slug que le seed système
        system_id = await conn.fetchval(
            "SELECT id FROM chunking_strategies WHERE slug='markdown-deep' AND owner_id IS NULL"
        )
        caller_id = await conn.fetchval(
            "SELECT id FROM chunking_strategies WHERE slug='markdown-deep' AND owner_id=$1",
            OWNER_A,
        )

    resolved = await resolve_caller_strategy(session_pool, owner_id=OWNER_A, slug="markdown-deep")
    assert resolved.id == caller_id != system_id

    # Un caller sans surcharge retombe sur le système.
    fallback = await resolve_caller_strategy(session_pool, owner_id=OWNER_B, slug="markdown-deep")
    assert fallback.id == system_id


@pytest.mark.asyncio
async def test_other_users_slug_is_invisible(session_pool: asyncpg.Pool) -> None:
    from rag.db.migrations import run_migrations

    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await _seed(conn, OWNER_A, "privee-a")

    with pytest.raises(UnknownStrategySlugError):
        await resolve_caller_strategy(session_pool, owner_id=OWNER_B, slug="privee-a")
    resolved = await resolve_caller_strategy(session_pool, owner_id=OWNER_A, slug="privee-a")
    assert resolved.algo == "prose"
