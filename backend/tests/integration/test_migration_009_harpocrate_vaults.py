from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_harpocrate_vaults_table_exists(session_pool: asyncpg.Pool):
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT to_regclass('public.harpocrate_vaults') AS table_oid")
    assert row["table_oid"] is not None


@pytest.mark.asyncio
async def test_unique_default_index(session_pool: asyncpg.Pool):
    """L'index unique partiel empêche deux coffres is_default=true simultanés."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    passphrase = "passphrase-of-at-least-32-characters-long"
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        await conn.execute(
            """
            INSERT INTO harpocrate_vaults (id, name, label, base_url, api_key_id,
                api_key_encrypted, is_default)
            VALUES (gen_random_uuid(), 'a', 'A', 'https://a', 'k1',
                pgp_sym_encrypt('secret', $1), true)
            """,
            passphrase,
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                """
                INSERT INTO harpocrate_vaults (id, name, label, base_url, api_key_id,
                    api_key_encrypted, is_default)
                VALUES (gen_random_uuid(), 'b', 'B', 'https://b', 'k2',
                    pgp_sym_encrypt('secret', $1), true)
                """,
                passphrase,
            )
        await conn.execute("DELETE FROM harpocrate_vaults")


@pytest.mark.asyncio
async def test_pgp_roundtrip(session_pool: asyncpg.Pool):
    """pgp_sym_encrypt + pgp_sym_decrypt avec la passphrase doit redonner la valeur claire."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    passphrase = "passphrase-of-at-least-32-characters-long"
    async with session_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pgp_sym_decrypt(
                pgp_sym_encrypt('the-secret-value', $1),
                $1
            )::text AS plain
            """,
            passphrase,
        )
    assert row["plain"] == "the-secret-value"
