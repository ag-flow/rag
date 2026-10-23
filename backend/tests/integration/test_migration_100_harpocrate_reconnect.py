"""Migration 100 : une demande « Connecter » peut cibler un coffre existant."""

from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

_INSERT_VAULT = (
    "INSERT INTO harpocrate_vaults (id, name, label, base_url, api_key_id, api_key_encrypted) "
    "VALUES (gen_random_uuid(), 'rag-m100', 'x', 'https://v', 'k', 'x'::bytea) RETURNING id"
)
_INSERT_REQUEST = (
    "INSERT INTO harpocrate_connect_requests (state_hash, binding_hash, owner_id, "
    "vault_name, vault_label, base_url, is_default, connect_state_encrypted, expires_at, "
    "vault_id) VALUES ($1, 'b', 'o', 'n', 'l', 'https://v', false, 'x'::bytea, now(), $2)"
)


@pytest.mark.asyncio
async def test_reconnect_request_follows_its_vault_and_creation_keeps_null_target(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_connect_requests")
        await conn.execute("DELETE FROM harpocrate_vaults WHERE name = 'rag-m100'")
        vault_id = await conn.fetchval(_INSERT_VAULT)
        await conn.execute(_INSERT_REQUEST, "creation", None)
        await conn.execute(_INSERT_REQUEST, "reconnexion", vault_id)
        row = await conn.fetchrow(
            "SELECT pending_key_encrypted, resolved_at FROM harpocrate_connect_requests "
            "WHERE state_hash = 'reconnexion'"
        )
        assert (row["pending_key_encrypted"], row["resolved_at"]) == (None, None)
        await conn.execute("DELETE FROM harpocrate_vaults WHERE id = $1", vault_id)
        remaining = await conn.fetch("SELECT state_hash FROM harpocrate_connect_requests")
    assert [r["state_hash"] for r in remaining] == ["creation"]
