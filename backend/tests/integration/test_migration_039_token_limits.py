from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_token_columns_added(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]: r["data_type"]
            for r in await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'model_dimensions'"
            )
        }
    assert "max_input_tokens" in cols
    assert cols["max_input_tokens"] == "integer"
    assert "token_char_ratio" in cols


@pytest.mark.asyncio
async def test_conservative_default_and_known_lower_limits(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        default_model = await conn.fetchrow(
            "SELECT max_input_tokens, token_char_ratio FROM model_dimensions "
            "WHERE provider='openai' AND model='text-embedding-3-small'"
        )
        mxbai = await conn.fetchval(
            "SELECT max_input_tokens FROM model_dimensions "
            "WHERE provider='ollama' AND model='mxbai-embed-large'"
        )
        gemini = await conn.fetchval(
            "SELECT max_input_tokens FROM model_dimensions "
            "WHERE provider='gemini' AND model='gemini-embedding-001'"
        )
    assert default_model["max_input_tokens"] == 8192
    assert default_model["token_char_ratio"] == Decimal("4.0")
    assert mxbai == 512
    assert gemini == 2048


@pytest.mark.asyncio
async def test_max_input_tokens_check_rejects_non_positive(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn, pytest.raises(asyncpg.CheckViolationError):
        await conn.execute(
            "INSERT INTO model_dimensions (provider, model, dimension, service, max_input_tokens) "
            "VALUES ('x', 'y', 10, 'x', 0)"
        )
