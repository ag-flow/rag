from __future__ import annotations

import uuid
from uuid import UUID

import asyncpg
import pytest

from rag.db.path_strategies import get_strategy, upsert_strategies_batch, upsert_strategy


@pytest.fixture
async def ws_id(migrated: asyncpg.Pool) -> UUID:
    """Insère un workspace minimal et retourne son id."""
    wid = uuid.uuid4()
    async with migrated.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO workspaces (id, name, rag_cnx)
            VALUES ($1, $2, 'postgresql://localhost/rag_test')
            """,
            wid,
            f"ws_{wid.hex[:8]}",
        )
    return wid


@pytest.mark.asyncio
async def test_get_strategy_default_replace(migrated: asyncpg.Pool, ws_id: UUID) -> None:
    result = await get_strategy(migrated, ws_id, "LESSONS.md")
    assert result == "replace"


@pytest.mark.asyncio
async def test_upsert_and_get_strategy(migrated: asyncpg.Pool, ws_id: UUID) -> None:
    await upsert_strategy(migrated, ws_id, "LESSONS.md", "append", "ui")
    result = await get_strategy(migrated, ws_id, "LESSONS.md")
    assert result == "append"


@pytest.mark.asyncio
async def test_upsert_idempotent(migrated: asyncpg.Pool, ws_id: UUID) -> None:
    await upsert_strategy(migrated, ws_id, "LESSONS.md", "append", "ui")
    await upsert_strategy(migrated, ws_id, "LESSONS.md", "replace", "strategy_file")
    result = await get_strategy(migrated, ws_id, "LESSONS.md")
    assert result == "replace"


@pytest.mark.asyncio
async def test_upsert_batch(migrated: asyncpg.Pool, ws_id: UUID) -> None:
    strategies = {"LESSONS.md": "append", "docs/CHANGELOG.md": "append"}
    await upsert_strategies_batch(migrated, ws_id, strategies)  # type: ignore[arg-type]
    assert await get_strategy(migrated, ws_id, "LESSONS.md") == "append"
    assert await get_strategy(migrated, ws_id, "docs/CHANGELOG.md") == "append"
    assert await get_strategy(migrated, ws_id, "other.md") == "replace"


@pytest.mark.asyncio
async def test_cascade_delete(migrated: asyncpg.Pool, ws_id: UUID) -> None:
    await upsert_strategy(migrated, ws_id, "LESSONS.md", "append", "ui")
    async with migrated.acquire() as conn:
        await conn.execute("DELETE FROM workspaces WHERE id=$1", ws_id)
    row = await migrated.fetchrow("SELECT * FROM path_strategies WHERE workspace_id=$1", ws_id)
    assert row is None
