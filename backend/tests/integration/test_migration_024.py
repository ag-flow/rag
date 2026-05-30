from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def test_migration_024_table_and_constraints(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        # Insérer un coffre minimal pour satisfaire la FK
        vault_id = await conn.fetchval(
            "INSERT INTO harpocrate_vaults "
            "(id, name, label, base_url, api_key_id, api_key_encrypted, is_default) "
            "VALUES (gen_random_uuid(), 'v024', 'V024', 'https://h.io', 'kid', 'enc', false) "
            "RETURNING id"
        )

        # Insertion normale
        pk_id = await conn.fetchval(
            "INSERT INTO provider_api_keys (key_id, label, provider, vault_id, harpo_path) "
            "VALUES ('my-key', 'My Key', 'openai', $1, '/v024/openai/my-key') "
            "RETURNING id",
            vault_id,
        )
        assert pk_id is not None

        # Contrainte UNIQUE (vault_id, provider, key_id)
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO provider_api_keys (key_id, label, provider, vault_id, harpo_path) "
                "VALUES ('my-key', 'Dup', 'openai', $1, '/v024/openai/my-key')",
                vault_id,
            )

        # ON DELETE RESTRICT : le coffre ne peut pas être supprimé
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await conn.execute(
                "DELETE FROM harpocrate_vaults WHERE id = $1", vault_id
            )
