from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_oidc_config_columns(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'oidc_config'"
            )
        }
    expected = {"id", "issuer", "client_id", "client_secret_ref", "created_at", "updated_at"}
    assert expected.issubset(cols)


@pytest.mark.asyncio
async def test_oidc_config_starts_empty(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM oidc_config")
        assert count == 0
