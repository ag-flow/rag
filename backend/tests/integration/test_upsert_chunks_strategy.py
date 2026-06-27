from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio
from pgvector.asyncpg import register_vector

from rag.db.workspace_embeddings import upsert_chunks
from rag.indexer.chunking import Chunk


@pytest_asyncio.fixture
async def ws_pool(pg_container: str) -> AsyncIterator[asyncpg.Pool]:
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    dbname = f"rag_test_strat_{uuid.uuid4().hex[:10]}"
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        await admin.close()

    ws_dsn = pg_container.rsplit("/", 1)[0] + f"/{dbname}"
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

    pool = await asyncpg.create_pool(
        ws_dsn, min_size=1, max_size=2,
        init=register_vector,
    )
    try:
        yield pool
    finally:
        await pool.close()
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        finally:
            await admin.close()


def _chunks(texts: list[str]) -> tuple[list[Chunk], list[list[float]]]:
    chunks = [Chunk(content=t, metadata={}) for t in texts]
    embeddings = [[0.1, 0.2, 0.3, 0.4]] * len(texts)
    return chunks, embeddings


@pytest.mark.asyncio
async def test_replace_strategy_overwrites(ws_pool: asyncpg.Pool) -> None:
    chunks_v1, embs_v1 = _chunks(["version 1"])
    await upsert_chunks(ws_pool, path="LESSONS.md", chunks=chunks_v1, embeddings=embs_v1, strategy="replace")
    chunks_v2, embs_v2 = _chunks(["version 2"])
    await upsert_chunks(ws_pool, path="LESSONS.md", chunks=chunks_v2, embeddings=embs_v2, strategy="replace")
    async with ws_pool.acquire() as conn:
        rows = await conn.fetch("SELECT content FROM embeddings WHERE path='LESSONS.md'")
    assert len(rows) == 1
    assert rows[0]["content"] == "version 2"


@pytest.mark.asyncio
async def test_append_strategy_accumulates(ws_pool: asyncpg.Pool) -> None:
    chunks_v1, embs_v1 = _chunks(["version 1"])
    await upsert_chunks(ws_pool, path="LESSONS.md", chunks=chunks_v1, embeddings=embs_v1, strategy="append")
    chunks_v2, embs_v2 = _chunks(["version 2"])
    await upsert_chunks(ws_pool, path="LESSONS.md", chunks=chunks_v2, embeddings=embs_v2, strategy="append")
    async with ws_pool.acquire() as conn:
        rows = await conn.fetch("SELECT content FROM embeddings WHERE path='LESSONS.md' ORDER BY id")
    contents = [r["content"] for r in rows]
    assert "version 1" in contents
    assert "version 2" in contents
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_append_two_batches_distinct_indexed_at(ws_pool: asyncpg.Pool) -> None:
    import asyncio
    chunks1, embs1 = _chunks(["lesson A"])
    await upsert_chunks(ws_pool, path="LESSONS.md", chunks=chunks1, embeddings=embs1, strategy="append")
    await asyncio.sleep(0.01)
    chunks2, embs2 = _chunks(["lesson B"])
    await upsert_chunks(ws_pool, path="LESSONS.md", chunks=chunks2, embeddings=embs2, strategy="append")
    async with ws_pool.acquire() as conn:
        rows = await conn.fetch("SELECT DISTINCT indexed_at FROM embeddings WHERE path='LESSONS.md'")
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_default_strategy_is_replace(ws_pool: asyncpg.Pool) -> None:
    chunks1, embs1 = _chunks(["v1"])
    await upsert_chunks(ws_pool, path="f.md", chunks=chunks1, embeddings=embs1)
    chunks2, embs2 = _chunks(["v2"])
    await upsert_chunks(ws_pool, path="f.md", chunks=chunks2, embeddings=embs2)
    async with ws_pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM embeddings WHERE path='f.md'")
    assert count == 1
