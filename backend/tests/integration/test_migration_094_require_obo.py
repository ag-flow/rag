"""Migration 094 : flag « OBO obligatoire » sur les clés API (epic f3cc98a8)."""

from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_require_obo_defaults_false_for_new_key(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        require_obo = await conn.fetchval(
            "INSERT INTO user_api_keys (owner_id, name, fingerprint) "
            "VALUES ('o094', 'k094', 'fp-094') RETURNING require_obo"
        )
    assert require_obo is False


@pytest.mark.asyncio
async def test_require_obo_rejects_null(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        with pytest.raises(asyncpg.NotNullViolationError):
            await conn.execute(
                "INSERT INTO user_api_keys (owner_id, name, fingerprint, require_obo) "
                "VALUES ('o094', 'k094-null', 'fp-094-null', NULL)"
            )
