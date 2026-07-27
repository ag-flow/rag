from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_user_api_keys_schema(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        keys_cols = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'user_api_keys'"
            )
        }
        old_table = await conn.fetchval(
            "SELECT to_regclass('workspace_api_keys')"
        )

    assert {"id", "owner_id", "name", "fingerprint", "revoked_at", "rotated_at"}.issubset(
        keys_cols
    )
    # Rebuild de zéro : l'ancienne table par workspace n'existe plus.
    assert old_table is None
    # NB : la table de grants user_api_key_workspaces (créée en 053) est
    # supprimée par la migration 067 — son absence est vérifiée dans
    # test_migration_067_user_api_key_scope.py.
