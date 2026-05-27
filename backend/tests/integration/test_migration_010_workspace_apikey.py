from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_workspaces_columns_after_010(session_pool: asyncpg.Pool) -> None:
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS indexer_configs, workspaces, schema_migrations CASCADE"
        )
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]: r["data_type"]
            for r in await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'workspaces'"
            )
        }
    assert "api_key_hash" not in cols
    assert cols.get("api_key_encrypted") == "bytea"
    assert cols.get("api_key_fingerprint") == "text"


@pytest.mark.asyncio
async def test_apikey_fingerprint_unique_index(session_pool: asyncpg.Pool) -> None:
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS indexer_configs, workspaces, schema_migrations CASCADE"
        )
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'workspaces' AND indexname = $1",
            "idx_workspaces_apikey_fingerprint",
        )
    assert row is not None


@pytest.mark.asyncio
async def test_apikey_roundtrip_via_pgcrypto(session_pool: asyncpg.Pool) -> None:
    """Round-trip : insert chiffré → SELECT pgp_sym_decrypt → valeur d'origine."""
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS indexer_configs, workspaces, schema_migrations CASCADE"
        )
    await run_migrations(session_pool, MIGRATIONS_DIR)

    dek = "abcdefghijklmnopqrstuvwxyz012345"
    api_key = "ws-key-original-clear"
    fp = sha256(api_key.encode()).hexdigest()
    async with session_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ($1, pgp_sym_encrypt($2::text, $3::text)::bytea, $4, 'c', 'b')",
            "ws_roundtrip", api_key, dek, fp,
        )
        decrypted = await conn.fetchval(
            "SELECT pgp_sym_decrypt(api_key_encrypted, $1::text)::text "
            "FROM workspaces WHERE name = $2",
            dek, "ws_roundtrip",
        )
    assert decrypted == api_key


@pytest.mark.asyncio
async def test_apikey_fingerprint_unique_violation(session_pool: asyncpg.Pool) -> None:
    """INSERT avec fingerprint déjà présent → UniqueViolationError."""
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS indexer_configs, workspaces, schema_migrations CASCADE"
        )
    await run_migrations(session_pool, MIGRATIONS_DIR)

    dek = "abcdefghijklmnopqrstuvwxyz012345"
    api_key = "duplicate-key"
    fp = sha256(api_key.encode()).hexdigest()
    async with session_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ($1, pgp_sym_encrypt($2::text, $3::text)::bytea, $4, 'c', 'b')",
            "ws_a", api_key, dek, fp,
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
                "VALUES ($1, pgp_sym_encrypt($2::text, $3::text)::bytea, $4, 'c', 'b')",
                "ws_b", api_key, dek, fp,
            )
