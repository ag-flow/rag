"""Migration 098 : table des demandes « Connecter à Harpocrate »."""

from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

_INSERT = (
    "INSERT INTO harpocrate_connect_requests (state_hash, binding_hash, owner_id, "
    "vault_name, vault_label, base_url, is_default, connect_state_encrypted, expires_at) "
    "VALUES ($1, 'b', 'o', 'n', 'l', 'https://v', false, 'x'::bytea, now())"
)


@pytest.mark.asyncio
async def test_connect_requests_state_hash_unique_and_consumed_nullable(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute(_INSERT, "h1")
        assert await conn.fetchval("SELECT consumed_at FROM harpocrate_connect_requests") is None
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(_INSERT, "h1")
