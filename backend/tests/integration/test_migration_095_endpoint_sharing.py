"""Migration 095 : partage des endpoints (epic f3cc98a8)."""

from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_endpoint_not_shared_by_default_and_share_cascades(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        vault_id = await conn.fetchval(
            "INSERT INTO harpocrate_vaults "
            "(id, name, label, base_url, api_key_id, api_key_encrypted) "
            "VALUES (gen_random_uuid(), 'v095', 'v095', 'https://harpo', 'k1', "
            "pgp_sym_encrypt('secret', 'passphrase-of-at-least-32-characters-long')) RETURNING id"
        )
        endpoint_id, shared = await conn.fetchrow(
            "INSERT INTO vault_endpoints (vault_id, label, slug, indexer_provider, indexer_model) "
            "VALUES ($1, 'ep', 'ep-095', 'openai', 'text-embedding-3-large') "
            "RETURNING id, shared_with_all",
            vault_id,
        )
        assert shared is False
        user_id = await conn.fetchval(
            "INSERT INTO users (username, email, password_hash) "
            "VALUES ('u095', 'u095@example.com', '') RETURNING id"
        )
        await conn.execute(
            "INSERT INTO vault_endpoint_shares (endpoint_id, user_id) VALUES ($1, $2)",
            endpoint_id,
            user_id,
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO vault_endpoint_shares (endpoint_id, user_id) VALUES ($1, $2)",
                endpoint_id,
                user_id,
            )
        await conn.execute("DELETE FROM vault_endpoints WHERE id = $1", endpoint_id)
        remaining = await conn.fetchval("SELECT count(*) FROM vault_endpoint_shares")
    assert remaining == 0
