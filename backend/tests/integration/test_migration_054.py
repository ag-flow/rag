from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_vault_endpoints_schema(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'vault_endpoints'"
            )
        }
    assert {
        "id", "vault_id", "label", "slug",
        "indexer_provider", "indexer_model", "indexer_api_key_ref", "indexer_base_url",
        "rerank_provider", "rerank_model", "rerank_api_key_ref", "rerank_base_url",
        "rerank_top_k",
    }.issubset(cols)
