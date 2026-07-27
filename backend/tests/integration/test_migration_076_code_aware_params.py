"""Migration 076 — retire heading_levels des stratégies code/data (résidu 042).

La 042 a basculé 'code-aware' de prose→code sans purger heading_levels : la
stratégie système explosait à l'exécution (unknown params for algo 'code').
"""

from __future__ import annotations

import json
from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_code_aware_has_no_heading_levels(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT slug, algo, params FROM chunking_strategies WHERE algo IN ('code','data')"
        )
    assert rows, "seed code-aware/data-structured attendu"
    for r in rows:
        params = json.loads(r["params"]) if isinstance(r["params"], str) else dict(r["params"])
        assert "heading_levels" not in params, f"{r['slug']} porte encore heading_levels"


@pytest.mark.asyncio
async def test_code_aware_builds_a_chunker(session_pool: asyncpg.Pool) -> None:
    """La stratégie système réparée passe la validation d'exécution."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    from rag.indexer.chunking.structured_factory import validate_strategy_spec

    async with session_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT algo, params FROM chunking_strategies "
            "WHERE slug = 'code-aware' AND owner_id IS NULL"
        )
    assert row is not None
    params = json.loads(row["params"]) if isinstance(row["params"], str) else dict(row["params"])
    validate_strategy_spec(algo=row["algo"], params=params, parser_slug=None)  # ne lève pas
