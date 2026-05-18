from __future__ import annotations

import asyncio

import asyncpg
import pytest

from rag.services.chunking_configs import (
    ChunkingConfigNotFound,
    get_chunking_config,
    upsert_chunking_config,
)
from tests.integration._workspace_seed import seed_workspace


@pytest.fixture
async def workspace_id(migrated: asyncpg.Pool) -> str:
    async with migrated.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_chunking_svc")
        await conn.execute(
            "INSERT INTO chunking_configs "
            "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
            "VALUES ($1, 'paragraph', 2000, 200, 200)",
            ws_id,
        )
    return ws_id


@pytest.mark.asyncio
async def test_get_returns_row(migrated: asyncpg.Pool, workspace_id: str) -> None:
    cfg = await get_chunking_config(workspace_id, migrated)
    assert cfg["strategy"] == "paragraph"
    assert cfg["max_chars"] == 2000
    assert cfg["min_chars"] == 200
    assert cfg["overlap_chars"] == 200
    assert cfg["extras"] == {}


@pytest.mark.asyncio
async def test_get_raises_when_missing(migrated: asyncpg.Pool) -> None:
    async with migrated.acquire() as conn:
        orphan_ws_id = await seed_workspace(
            conn,
            name="ws_no_config",
            api_key="orphan-key",
        )
    with pytest.raises(ChunkingConfigNotFound):
        await get_chunking_config(orphan_ws_id, migrated)


@pytest.mark.asyncio
async def test_upsert_updates_existing(
    migrated: asyncpg.Pool,
    workspace_id: str,
) -> None:
    cfg = await upsert_chunking_config(
        migrated,
        workspace_id=workspace_id,
        strategy="paragraph",
        max_chars=1500,
        min_chars=100,
        overlap_chars=150,
        extras={},
    )
    assert cfg["max_chars"] == 1500
    assert cfg["min_chars"] == 100
    assert cfg["overlap_chars"] == 150


@pytest.mark.asyncio
async def test_upsert_inserts_when_absent(migrated: asyncpg.Pool) -> None:
    async with migrated.acquire() as conn:
        ws_id = await seed_workspace(
            conn,
            name="ws_upsert_new",
            api_key="upsert-new-key",
        )
    cfg = await upsert_chunking_config(
        migrated,
        workspace_id=ws_id,
        strategy="paragraph",
        max_chars=800,
        min_chars=80,
        overlap_chars=80,
        extras={},
    )
    assert cfg["max_chars"] == 800


@pytest.mark.asyncio
async def test_upsert_updates_updated_at(
    migrated: asyncpg.Pool,
    workspace_id: str,
) -> None:
    cfg_before = await get_chunking_config(workspace_id, migrated)
    await asyncio.sleep(0.05)
    cfg_after = await upsert_chunking_config(
        migrated,
        workspace_id=workspace_id,
        strategy="paragraph",
        max_chars=1234,
        min_chars=100,
        overlap_chars=100,
        extras={},
    )
    assert cfg_after["updated_at"] > cfg_before["updated_at"]


@pytest.mark.asyncio
async def test_fk_cascade_on_workspace_delete(
    migrated: asyncpg.Pool,
    workspace_id: str,
) -> None:
    async with migrated.acquire() as conn:
        await conn.execute("DELETE FROM workspaces WHERE id = $1", workspace_id)
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM chunking_configs WHERE workspace_id = $1",
            workspace_id,
        )
    assert count == 0


@pytest.mark.asyncio
async def test_upsert_extras_default_empty_dict(
    migrated: asyncpg.Pool,
    workspace_id: str,
) -> None:
    """extras=None / {} both roundtrip as {}."""
    cfg = await upsert_chunking_config(
        migrated,
        workspace_id=workspace_id,
        strategy="paragraph",
        max_chars=500,
        min_chars=50,
        overlap_chars=50,
        extras={},
    )
    assert cfg["extras"] == {}
