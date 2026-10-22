"""Migration 097 : stratégie et prompt système d'exemple pour une doc docflow."""

from __future__ import annotations

import json
from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.indexer.chunking.structured_factory import validate_strategy_spec

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_docflow_docs_strategy_seeded_as_valid_system_prose(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    row = await session_pool.fetchrow(
        "SELECT label, algo, params, parser_slug FROM chunking_strategies "
        "WHERE slug = 'docflow-docs' AND owner_id IS NULL AND workspace_id IS NULL"
    )
    assert row is not None
    params = json.loads(row["params"]) if isinstance(row["params"], str) else row["params"]
    assert (row["label"], row["algo"], row["parser_slug"]) == ("docflow-docs", "prose", None)
    assert params == {
        "child_target_tokens": 384,
        "floor_tokens": 32,
        "overlap_tokens": 64,
        "breadcrumb_depth": -1,
        "heading_levels": [1, 2, 3],
    }
    # Une stratégie système invalide casserait toute indexation qui la résout.
    validate_strategy_spec(algo=row["algo"], params=params, parser_slug=row["parser_slug"])


@pytest.mark.asyncio
async def test_docflow_docs_context_prompt_seeded_with_chunk_placeholder_and_unbound(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    row = await session_pool.fetchrow(
        "SELECT id, language, metadata_key, result_type, target, timing, prompt "
        "FROM prompt_templates "
        "WHERE name = 'docflow-docs-contexte-chunk' AND owner_id IS NULL"
    )
    assert row is not None
    assert (row["language"], row["metadata_key"], row["result_type"]) == (
        "fr-FR",
        "context",
        "text",
    )
    assert (row["target"], row["timing"]) == ("chunk", "embedding_inline")
    assert "{chunk}" in row["prompt"]
    bound = await session_pool.fetchval(
        "SELECT count(*) FROM chunking_strategy_prompts WHERE template_id = $1", row["id"]
    )
    assert bound == 0
