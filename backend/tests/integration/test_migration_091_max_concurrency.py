"""Migration 091 : limite de requêtes parallèles par service d'endpoint
(enabler a7e2ec90 — enforcement cross-workspace, NULL = pas de limite)."""

from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_columns_default_null_and_check(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        vault_id = await conn.fetchval(
            "INSERT INTO harpocrate_vaults (name, label, base_url, api_key_id, api_key_encrypted) "
            "VALUES ('v091', 'v091', 'https://harpo', 'k1', "
            "pgp_sym_encrypt('secret', 'passphrase-of-at-least-32-characters-long')) RETURNING id"
        )
        row = await conn.fetchrow(
            "INSERT INTO vault_endpoints (vault_id, label, slug, indexer_provider, indexer_model, "
            "indexer_max_concurrency) "
            "VALUES ($1, 'ep', 'ep-091', 'openai', 'text-embedding-3-large', 4) "
            "RETURNING indexer_max_concurrency, rerank_max_concurrency, llm_max_concurrency",
            vault_id,
        )
        assert row["indexer_max_concurrency"] == 4
        assert row["rerank_max_concurrency"] is None
        assert row["llm_max_concurrency"] is None

        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "UPDATE vault_endpoints SET llm_max_concurrency = 0 WHERE slug = 'ep-091'"
            )
