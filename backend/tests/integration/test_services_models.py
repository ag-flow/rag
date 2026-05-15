from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.api.errors import ModelInUse, ModelNotSupported
from rag.db.migrations import run_migrations
from rag.services.models import (
    add_model,
    delete_model,
    get_dimension_or_raise,
    list_models,
)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_list_models_returns_seed(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    entries = await list_models(session_pool)
    couples = {(e.provider, e.model) for e in entries}
    assert ("openai", "text-embedding-3-small") in couples
    assert ("ollama", "nomic-embed-text") in couples


@pytest.mark.asyncio
async def test_add_model_inserts_row(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    await add_model(session_pool, provider="custom", model="m-1", dimension=512)
    rows = await list_models(session_pool)
    assert any(e.provider == "custom" and e.model == "m-1" and e.dimension == 512 for e in rows)


@pytest.mark.asyncio
async def test_add_model_duplicate_raises(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    with pytest.raises(asyncpg.UniqueViolationError):
        await add_model(
            session_pool, provider="openai", model="text-embedding-3-small", dimension=1536
        )


@pytest.mark.asyncio
async def test_delete_model_removes_row(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    await add_model(session_pool, provider="custom", model="m-2", dimension=256)
    await delete_model(session_pool, provider="custom", model="m-2")
    rows = await list_models(session_pool)
    assert not any(e.provider == "custom" and e.model == "m-2" for e in rows)


@pytest.mark.asyncio
async def test_delete_model_raises_when_in_use(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ('ws_uses_voyage', 'h', 'c', 'b') RETURNING id"
        )
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'voyage', 'voyage-3', 1024)",
            ws_id,
        )

    with pytest.raises(ModelInUse) as exc_info:
        await delete_model(session_pool, provider="voyage", model="voyage-3")
    assert "ws_uses_voyage" in exc_info.value.workspaces


@pytest.mark.asyncio
async def test_get_dimension_or_raise_returns_dim(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    dim = await get_dimension_or_raise(
        session_pool, provider="openai", model="text-embedding-3-small"
    )
    assert dim == 1536


@pytest.mark.asyncio
async def test_get_dimension_or_raise_unknown_model_raises(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    with pytest.raises(ModelNotSupported) as exc_info:
        await get_dimension_or_raise(session_pool, provider="nope", model="nope")
    assert exc_info.value.provider == "nope"
    # supported doit contenir au moins openai/text-embedding-3-small
    assert any(p == "openai" for (p, _) in exc_info.value.supported)
