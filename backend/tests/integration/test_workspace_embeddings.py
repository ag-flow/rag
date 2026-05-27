from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio
from pgvector.asyncpg import register_vector

from rag.db.workspace_embeddings import (
    delete_chunks_for_path,
    delete_path,
    upsert_chunks,
)
from rag.indexer.chunking import Chunk


@pytest_asyncio.fixture
async def ws_pool_with_embeddings(
    pg_container: str,
) -> AsyncIterator[asyncpg.Pool]:
    """Crée une base workspace test (pgvector + table embeddings) et yield un pool."""
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    dbname = f"rag_test_emb_{uuid.uuid4().hex[:10]}"

    # CREATE DATABASE via admin
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        await admin.close()

    ws_dsn = pg_container.rsplit("/", 1)[0] + f"/{dbname}"

    # Setup schema dans la nouvelle DB
    setup = await asyncpg.connect(ws_dsn)
    try:
        await setup.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await setup.execute(
            """
            CREATE TABLE embeddings (
                id           SERIAL PRIMARY KEY,
                path         TEXT NOT NULL,
                chunk_index  INT  NOT NULL,
                content      TEXT NOT NULL,
                embedding    vector(4) NOT NULL,
                metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
                indexed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (path, chunk_index)
            )
            """
        )
    finally:
        await setup.close()

    # Pool avec pgvector enregistré sur chaque connexion
    pool = await asyncpg.create_pool(
        ws_dsn,
        min_size=1,
        max_size=4,
        init=register_vector,
    )

    try:
        yield pool
    finally:
        await pool.close()
        # Drop la DB de test
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        finally:
            await admin.close()


@pytest.mark.asyncio
async def test_upsert_chunks_inserts_n_rows(
    ws_pool_with_embeddings: asyncpg.Pool,
) -> None:
    count = await upsert_chunks(
        ws_pool_with_embeddings,
        path="docs/a.md",
        chunks=[Chunk(content="chunk 1"), Chunk(content="chunk 2"), Chunk(content="chunk 3")],
        embeddings=[[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]],
    )
    assert count == 3
    rows = await ws_pool_with_embeddings.fetch(
        "SELECT path, chunk_index, content FROM embeddings ORDER BY chunk_index"
    )
    assert len(rows) == 3
    assert [r["chunk_index"] for r in rows] == [0, 1, 2]
    assert rows[0]["content"] == "chunk 1"


@pytest.mark.asyncio
async def test_upsert_chunks_replaces_existing_for_same_path(
    ws_pool_with_embeddings: asyncpg.Pool,
) -> None:
    await upsert_chunks(
        ws_pool_with_embeddings,
        path="a.md",
        chunks=[Chunk(content="v1-c0"), Chunk(content="v1-c1"), Chunk(content="v1-c2")],
        embeddings=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]],
    )
    # Upsert v2 avec MOINS de chunks
    await upsert_chunks(
        ws_pool_with_embeddings,
        path="a.md",
        chunks=[Chunk(content="v2-c0"), Chunk(content="v2-c1")],
        embeddings=[[0, 1, 0, 0], [0, 0, 1, 0]],
    )
    rows = await ws_pool_with_embeddings.fetch(
        "SELECT chunk_index, content FROM embeddings WHERE path='a.md' ORDER BY chunk_index"
    )
    assert len(rows) == 2
    assert [r["content"] for r in rows] == ["v2-c0", "v2-c1"]


@pytest.mark.asyncio
async def test_upsert_chunks_other_paths_untouched(
    ws_pool_with_embeddings: asyncpg.Pool,
) -> None:
    await upsert_chunks(
        ws_pool_with_embeddings,
        path="a.md",
        chunks=[Chunk(content="a-c0")],
        embeddings=[[1, 0, 0, 0]],
    )
    await upsert_chunks(
        ws_pool_with_embeddings,
        path="b.md",
        chunks=[Chunk(content="b-c0")],
        embeddings=[[0, 1, 0, 0]],
    )
    # Upsert sur a.md ne doit pas toucher b.md
    await upsert_chunks(
        ws_pool_with_embeddings,
        path="a.md",
        chunks=[Chunk(content="a-c0-new")],
        embeddings=[[0, 0, 1, 0]],
    )
    b_content = await ws_pool_with_embeddings.fetchval(
        "SELECT content FROM embeddings WHERE path='b.md'"
    )
    assert b_content == "b-c0"


@pytest.mark.asyncio
async def test_upsert_chunks_mismatched_lengths_raises(
    ws_pool_with_embeddings: asyncpg.Pool,
) -> None:
    with pytest.raises(ValueError, match=r"chunks.*embeddings"):
        await upsert_chunks(
            ws_pool_with_embeddings,
            path="a.md",
            chunks=[Chunk(content="c0"), Chunk(content="c1")],
            embeddings=[[1, 0, 0, 0]],
        )


@pytest.mark.asyncio
async def test_delete_chunks_for_path_removes_all_chunks(
    ws_pool_with_embeddings: asyncpg.Pool,
) -> None:
    await upsert_chunks(
        ws_pool_with_embeddings,
        path="a.md",
        chunks=[Chunk(content="c0"), Chunk(content="c1")],
        embeddings=[[1, 0, 0, 0], [0, 1, 0, 0]],
    )
    deleted = await delete_chunks_for_path(ws_pool_with_embeddings, "a.md")
    assert deleted == 2
    rows = await ws_pool_with_embeddings.fetch("SELECT 1 FROM embeddings WHERE path='a.md'")
    assert rows == []


@pytest.mark.asyncio
async def test_delete_chunks_for_absent_path_returns_zero(
    ws_pool_with_embeddings: asyncpg.Pool,
) -> None:
    deleted = await delete_chunks_for_path(ws_pool_with_embeddings, "ghost.md")
    assert deleted == 0


@pytest.mark.asyncio
async def test_upsert_chunks_empty_list_deletes_existing_and_returns_zero(
    ws_pool_with_embeddings: asyncpg.Pool,
) -> None:
    """Si chunks=[], on supprime ce qui existait et on retourne 0 (cas degenere)."""
    # Setup : insere 2 chunks
    await upsert_chunks(
        ws_pool_with_embeddings,
        path="a.md",
        chunks=[Chunk(content="c0"), Chunk(content="c1")],
        embeddings=[[1, 0, 0, 0], [0, 1, 0, 0]],
    )
    # Upsert avec chunks=[] doit supprimer et retourner 0
    count = await upsert_chunks(
        ws_pool_with_embeddings,
        path="a.md",
        chunks=[],
        embeddings=[],
    )
    assert count == 0
    rows = await ws_pool_with_embeddings.fetch("SELECT 1 FROM embeddings WHERE path='a.md'")
    assert rows == []


@pytest.mark.asyncio
async def test_delete_path_alias_works(
    ws_pool_with_embeddings: asyncpg.Pool,
) -> None:
    """delete_path est l'alias sémantique consommé par RealIndexer.delete_file."""
    await upsert_chunks(
        ws_pool_with_embeddings,
        path="a.md",
        chunks=[Chunk(content="c")],
        embeddings=[[1, 0, 0, 0]],
    )
    await delete_path(ws_pool_with_embeddings, "a.md")
    rows = await ws_pool_with_embeddings.fetch("SELECT 1 FROM embeddings")
    assert rows == []
