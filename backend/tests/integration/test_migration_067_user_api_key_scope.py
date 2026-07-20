from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_scope_column_and_grants_table_dropped(session_pool: asyncpg.Pool) -> None:
    """Migration 067 : scope IN (read,read_write,admin) défaut 'read',
    et la table de grants par workspace disparaît."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        scope_default = await conn.fetchval(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'user_api_keys' AND column_name = 'scope'"
        )
        grants_table = await conn.fetchval(
            "SELECT to_regclass('user_api_key_workspaces')"
        )

    # La colonne scope existe et défaut sur 'read'.
    assert scope_default is not None
    assert "read" in scope_default
    # La table de grants par workspace est supprimée par 067.
    assert grants_table is None


@pytest.mark.asyncio
async def test_scope_check_constraint_rejects_invalid(session_pool: asyncpg.Pool) -> None:
    """Le CHECK n'accepte que read / read_write / admin."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        for scope in ("read", "read_write", "admin"):
            key_id = await conn.fetchval(
                "INSERT INTO user_api_keys (owner_id, name, fingerprint, scope) "
                "VALUES ($1, $2, $3, $4) RETURNING id",
                f"owner-{scope}", f"key-{scope}", f"fp-{scope}", scope,
            )
            assert key_id is not None

        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO user_api_keys (owner_id, name, fingerprint, scope) "
                "VALUES ($1, $2, $3, $4)",
                "owner-bad", "key-bad", "fp-bad", "superuser",
            )
