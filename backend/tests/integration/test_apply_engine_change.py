from __future__ import annotations

import asyncpg
import pytest

from rag.api.errors import ChunkingChangeRequiresReindex, WorkspaceNotFound
from rag.services.jobs import apply_engine_change
from tests.integration._workspace_seed import seed_workspace


async def _seed_ws_with_config(conn: asyncpg.Connection, name: str) -> str:
    ws_id = await seed_workspace(conn, name=name)
    await conn.execute(
        "INSERT INTO chunking_configs "
        "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
        "VALUES ($1, 'paragraph', 2000, 200, 200)",
        ws_id,
    )
    return str(ws_id)


@pytest.mark.asyncio
async def test_unknown_workspace_raises(migrated: asyncpg.Pool) -> None:
    with pytest.raises(WorkspaceNotFound):
        await apply_engine_change(
            name="nope", engine="structured", confirm=False, config_pool=migrated
        )


@pytest.mark.asyncio
async def test_invalid_engine_rejected(migrated: asyncpg.Pool) -> None:
    with pytest.raises(ValueError, match="invalid engine"):
        await apply_engine_change(
            name="x", engine="turbo", confirm=False, config_pool=migrated
        )


@pytest.mark.asyncio
async def test_same_engine_is_no_change(migrated: asyncpg.Pool) -> None:
    async with migrated.acquire() as conn:
        await _seed_ws_with_config(conn, "ws_engine_noop")
    result = await apply_engine_change(
        name="ws_engine_noop", engine="legacy", confirm=False, config_pool=migrated
    )
    assert result == "no_change"


@pytest.mark.asyncio
async def test_zero_docs_switches_without_reindex(migrated: asyncpg.Pool) -> None:
    async with migrated.acquire() as conn:
        ws_id = await _seed_ws_with_config(conn, "ws_engine_zero")
    result = await apply_engine_change(
        name="ws_engine_zero", engine="structured", confirm=False, config_pool=migrated
    )
    assert result[0] == "updated"
    engine = await migrated.fetchval(
        "SELECT engine FROM chunking_configs WHERE workspace_id=$1", ws_id
    )
    assert engine == "structured"


@pytest.mark.asyncio
async def test_docs_without_confirm_requires_reindex(migrated: asyncpg.Pool) -> None:
    async with migrated.acquire() as conn:
        ws_id = await _seed_ws_with_config(conn, "ws_engine_confirm")
        await conn.execute(
            "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
            "VALUES ($1, 'a.md', 'sha256:x', 'p/m')",
            ws_id,
        )
    with pytest.raises(ChunkingChangeRequiresReindex):
        await apply_engine_change(
            name="ws_engine_confirm", engine="structured", confirm=False, config_pool=migrated
        )


@pytest.mark.asyncio
async def test_docs_with_confirm_invalidates_and_enqueues(migrated: asyncpg.Pool) -> None:
    async with migrated.acquire() as conn:
        ws_id = await _seed_ws_with_config(conn, "ws_engine_go")
        await conn.execute(
            "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
            "VALUES ($1, 'a.md', 'sha256:x', 'p/m')",
            ws_id,
        )
    result = await apply_engine_change(
        name="ws_engine_go", engine="structured", confirm=True, config_pool=migrated
    )
    assert result[0] == "reindex_triggered"

    engine = await migrated.fetchval(
        "SELECT engine FROM chunking_configs WHERE workspace_id=$1", ws_id
    )
    docs = await migrated.fetchval(
        "SELECT COUNT(*) FROM indexed_documents WHERE workspace_id=$1", ws_id
    )
    job = await migrated.fetchval(
        "SELECT triggered_by FROM index_jobs WHERE workspace_id=$1 ORDER BY id DESC LIMIT 1",
        ws_id,
    )
    assert engine == "structured"
    assert docs == 0  # indexed_documents invalidé → re-chunk au pull suivant
    assert job == "reindex_chunking_change"
