from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.api.errors import ModelInUse, ModelNotOwned, ModelNotSupported
from rag.db.migrations import run_migrations
from rag.services.models import (
    add_model,
    delete_model,
    get_dimension_or_raise,
    list_models,
)
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

OWNER_A = "owner-a-hash"
OWNER_B = "owner-b-hash"


@pytest.mark.asyncio
async def test_list_models_returns_seed(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    entries = await list_models(session_pool, owner_id=OWNER_A)
    couples = {(e.provider, e.model) for e in entries}
    assert ("openai", "text-embedding-3-small") in couples
    assert ("ollama", "nomic-embed-text") in couples


@pytest.mark.asyncio
async def test_add_model_inserts_row(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    await add_model(session_pool, provider="custom", model="m-1", dimension=512, owner_id=OWNER_A)
    rows = await list_models(session_pool, owner_id=OWNER_A)
    assert any(e.provider == "custom" and e.model == "m-1" and e.dimension == 512 for e in rows)


@pytest.mark.asyncio
async def test_add_model_duplicate_raises(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    with pytest.raises(asyncpg.UniqueViolationError):
        await add_model(
            session_pool,
            provider="openai",
            model="text-embedding-3-small",
            dimension=1536,
            owner_id=OWNER_A,
        )


@pytest.mark.asyncio
async def test_delete_model_removes_row(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    await add_model(session_pool, provider="custom", model="m-2", dimension=256, owner_id=OWNER_A)
    await delete_model(session_pool, provider="custom", model="m-2", owner_id=OWNER_A)
    rows = await list_models(session_pool, owner_id=OWNER_A)
    assert not any(e.provider == "custom" and e.model == "m-2" for e in rows)


@pytest.mark.asyncio
async def test_delete_model_raises_when_in_use(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    await add_model(
        session_pool, provider="custom", model="m-inuse", dimension=64, owner_id=OWNER_A
    )
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(
            conn, name="ws_uses_custom", rag_cnx="postgresql://test/c", rag_base="b"
        )
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'custom', 'm-inuse', 64)",
            ws_id,
        )

    with pytest.raises(ModelInUse) as exc_info:
        await delete_model(session_pool, provider="custom", model="m-inuse", owner_id=OWNER_A)
    assert "ws_uses_custom" in exc_info.value.workspaces


@pytest.mark.asyncio
async def test_delete_seed_model_raises_system_immutable(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    with pytest.raises(ModelNotOwned) as exc_info:
        await delete_model(session_pool, provider="voyage", model="voyage-3", owner_id=OWNER_A)
    assert exc_info.value.is_system is True


@pytest.mark.asyncio
async def test_delete_other_users_model_raises_not_owned(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    await add_model(session_pool, provider="custom", model="m-of-b", dimension=32, owner_id=OWNER_B)
    with pytest.raises(ModelNotOwned) as exc_info:
        await delete_model(session_pool, provider="custom", model="m-of-b", owner_id=OWNER_A)
    assert exc_info.value.is_system is False


@pytest.mark.asyncio
async def test_list_models_hides_other_users_models(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    await add_model(
        session_pool, provider="custom", model="m-priv-b", dimension=32, owner_id=OWNER_B
    )
    rows_a = await list_models(session_pool, owner_id=OWNER_A)
    rows_b = await list_models(session_pool, owner_id=OWNER_B)
    assert not any(e.model == "m-priv-b" for e in rows_a)
    assert any(e.model == "m-priv-b" and e.is_system is False for e in rows_b)
    assert all(e.is_system for e in rows_a if e.provider == "openai")


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
