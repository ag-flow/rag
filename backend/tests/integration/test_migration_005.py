from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_model_dimensions_table_created(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        regclass = await conn.fetchval("SELECT to_regclass('public.model_dimensions')::text")
    assert regclass == "model_dimensions"


@pytest.mark.asyncio
async def test_model_dimensions_seed_present(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT provider, model, dimension FROM model_dimensions ORDER BY provider, model"
        )
    seeded = {(r["provider"], r["model"], r["dimension"]) for r in rows}
    assert ("openai", "text-embedding-3-small", 1536) in seeded
    assert ("openai", "text-embedding-3-large", 3072) in seeded
    assert ("voyage", "voyage-3", 1024) in seeded
    assert ("voyage", "voyage-code-3", 1024) in seeded
    assert ("ollama", "qwen2.5-coder:14b", 4096) in seeded
    assert ("ollama", "nomic-embed-text", 768) in seeded


@pytest.mark.asyncio
async def test_model_dimensions_primary_key(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO model_dimensions (provider, model, dimension) "
                "VALUES ('openai', 'text-embedding-3-small', 9999)"
            )


@pytest.mark.asyncio
async def test_model_dimensions_check_constraint(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO model_dimensions (provider, model, dimension) "
                "VALUES ('test', 'bad', 0)"
            )
