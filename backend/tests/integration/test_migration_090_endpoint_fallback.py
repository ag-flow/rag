"""Migration 090 : fallback d'endpoint + paramètres du circuit breaker sur
`vault_endpoints` (enabler docflow f94bfd84)."""

from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


_PASSPHRASE = "passphrase-of-at-least-32-characters-long"


async def _seed_vault_and_endpoint(
    conn: asyncpg.Connection, *, vault_name: str, slug: str
) -> tuple[str, str]:
    vault_id = await conn.fetchval(
        "INSERT INTO harpocrate_vaults (name, label, base_url, api_key_id, api_key_encrypted) "
        "VALUES ($1, $1, 'https://harpo', 'k1', pgp_sym_encrypt('secret', $2)) RETURNING id",
        vault_name,
        _PASSPHRASE,
    )
    endpoint_id = await conn.fetchval(
        "INSERT INTO vault_endpoints (vault_id, label, slug, indexer_provider, indexer_model) "
        "VALUES ($1, $2, $2, 'openai', 'text-embedding-3-large') RETURNING id",
        vault_id,
        slug,
    )
    return str(vault_id), str(endpoint_id)


@pytest.mark.asyncio
async def test_columns_and_defaults(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        _, ep = await _seed_vault_and_endpoint(conn, vault_name="v090a", slug="ep-090a")
        row = await conn.fetchrow(
            "SELECT fallback_endpoint_id, failure_threshold, cooldown_seconds "
            "FROM vault_endpoints WHERE id = $1::uuid",
            ep,
        )
    assert row["fallback_endpoint_id"] is None
    assert row["failure_threshold"] == 3
    assert row["cooldown_seconds"] == 60


@pytest.mark.asyncio
async def test_self_fallback_rejected_by_check(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        _, ep = await _seed_vault_and_endpoint(conn, vault_name="v090b", slug="ep-090b")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "UPDATE vault_endpoints SET fallback_endpoint_id = $1::uuid WHERE id = $1::uuid",
                ep,
            )


@pytest.mark.asyncio
async def test_fallback_deletion_sets_null(session_pool: asyncpg.Pool) -> None:
    """ON DELETE SET NULL : supprimer le fallback ne casse pas le primaire."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        vault_id, primary = await _seed_vault_and_endpoint(conn, vault_name="v090c", slug="ep-090c")
        mirror = await conn.fetchval(
            "INSERT INTO vault_endpoints (vault_id, label, slug, indexer_provider, indexer_model) "
            "VALUES ($1::uuid, 'Mirror', 'ep-090c-mirror', 'ollama', 'text-embedding-3-large') "
            "RETURNING id",
            vault_id,
        )
        await conn.execute(
            "UPDATE vault_endpoints SET fallback_endpoint_id = $2 WHERE id = $1::uuid",
            primary,
            mirror,
        )
        await conn.execute("DELETE FROM vault_endpoints WHERE id = $1", mirror)
        remaining = await conn.fetchval(
            "SELECT fallback_endpoint_id FROM vault_endpoints WHERE id = $1::uuid", primary
        )
    assert remaining is None
