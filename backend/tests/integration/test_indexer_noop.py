from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.indexer.noop import NoOpIndexer
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_noop_index_file_inserts_indexed_documents_row(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_noop_a", rag_cnx="c", rag_base="b")

    indexer = NoOpIndexer(session_pool)
    chunks = await indexer.index_file(
        workspace_id=ws_id,
        path="docs/README.md",
        content="hello",
        content_hash="sha256:abc",
        indexer_used="openai/text-embedding-3-small",
    )
    assert chunks == 1

    row = await session_pool.fetchrow(
        "SELECT content_hash, indexer_used FROM indexed_documents "
        "WHERE workspace_id=$1 AND path=$2",
        ws_id,
        "docs/README.md",
    )
    assert row is not None
    assert row["content_hash"] == "sha256:abc"
    assert row["indexer_used"] == "openai/text-embedding-3-small"


@pytest.mark.asyncio
async def test_noop_index_file_updates_on_conflict(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_noop_b", rag_cnx="c", rag_base="b")

    indexer = NoOpIndexer(session_pool)
    await indexer.index_file(
        workspace_id=ws_id,
        path="a.md",
        content="v1",
        content_hash="sha256:v1",
        indexer_used="openai/text-embedding-3-small",
    )
    await indexer.index_file(
        workspace_id=ws_id,
        path="a.md",
        content="v2",
        content_hash="sha256:v2",
        indexer_used="openai/text-embedding-3-small",
    )

    rows = await session_pool.fetch(
        "SELECT content_hash FROM indexed_documents WHERE workspace_id=$1 AND path='a.md'",
        ws_id,
    )
    assert len(rows) == 1
    assert rows[0]["content_hash"] == "sha256:v2"


@pytest.mark.asyncio
async def test_noop_delete_file_removes_row(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_noop_c", rag_cnx="c", rag_base="b")

    indexer = NoOpIndexer(session_pool)
    await indexer.index_file(
        workspace_id=ws_id,
        path="x.md",
        content="x",
        content_hash="sha256:x",
        indexer_used="openai/text-embedding-3-small",
    )
    await indexer.delete_file(workspace_id=ws_id, path="x.md")

    row = await session_pool.fetchrow(
        "SELECT 1 FROM indexed_documents WHERE workspace_id=$1 AND path='x.md'",
        ws_id,
    )
    assert row is None


@pytest.mark.asyncio
async def test_noop_delete_file_idempotent_when_absent(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    # Pas d'INSERT préalable. Le delete doit ne rien faire et ne pas lever.
    indexer = NoOpIndexer(session_pool)
    await indexer.delete_file(workspace_id=uuid4(), path="absent.md")
