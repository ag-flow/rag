from __future__ import annotations

import asyncpg
import pytest

from rag.db.workspace_migrations import apply_pending


async def _legacy_embeddings(dsn: str) -> None:
    """Recrée la table embeddings telle que `create_embeddings_table` la pose
    (avant migrations workspace), + une ligne legacy."""
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(
            "CREATE TABLE embeddings ("
            "id SERIAL PRIMARY KEY, path TEXT NOT NULL, "
            "chunk_index INT NOT NULL, content TEXT NOT NULL, "
            "embedding vector(8) NOT NULL, "
            "indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
            "UNIQUE (path, chunk_index))"
        )
        await conn.execute(
            "INSERT INTO embeddings (path, chunk_index, content, embedding) "
            "VALUES ('a.md', 0, 'hello', $1::vector)",
            str([0.0] * 8),
        )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_sections_table_and_new_columns(workspace_test_db: tuple[str, str]) -> None:
    _, dsn = workspace_test_db
    await _legacy_embeddings(dsn)
    await apply_pending(dsn)

    conn = await asyncpg.connect(dsn)
    try:
        cols = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'embeddings'"
            )
        }
        sections_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'sections')"
        )
        legacy = await conn.fetchrow("SELECT content, chunk_hash FROM embeddings WHERE path='a.md'")
    finally:
        await conn.close()

    assert {"section_id", "chunk_hash"} <= cols
    assert sections_exists is True
    assert legacy["content"] == "hello"
    assert legacy["chunk_hash"] is None  # ligne legacy préservée, hash NULL


@pytest.mark.asyncio
async def test_old_chunk_index_unique_dropped(workspace_test_db: tuple[str, str]) -> None:
    """Deux lignes même path / même chunk_index sont désormais permises
    (chunk_index n'est plus une identité)."""
    _, dsn = workspace_test_db
    await _legacy_embeddings(dsn)
    await apply_pending(dsn)

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "INSERT INTO embeddings (path, chunk_index, content, embedding) "
            "VALUES ('a.md', 0, 'dup', $1::vector)",
            str([0.0] * 8),
        )
        count = await conn.fetchval("SELECT COUNT(*) FROM embeddings WHERE path='a.md'")
    finally:
        await conn.close()
    assert count == 2


@pytest.mark.asyncio
async def test_partial_unique_on_chunk_hash(workspace_test_db: tuple[str, str]) -> None:
    _, dsn = workspace_test_db
    await _legacy_embeddings(dsn)
    await apply_pending(dsn)

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "INSERT INTO embeddings (path, chunk_index, content, embedding, chunk_hash) "
            "VALUES ('b.md', 0, 'x', $1::vector, 'h1')",
            str([0.0] * 8),
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO embeddings (path, chunk_index, content, embedding, chunk_hash) "
                "VALUES ('b.md', 1, 'y', $1::vector, 'h1')",  # même (path, chunk_hash)
                str([0.0] * 8),
            )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_section_fk_cascade(workspace_test_db: tuple[str, str]) -> None:
    _, dsn = workspace_test_db
    await _legacy_embeddings(dsn)
    await apply_pending(dsn)

    conn = await asyncpg.connect(dsn)
    try:
        sec_id = await conn.fetchval(
            "INSERT INTO sections (path, section_key, content) "
            "VALUES ('c.md', 'Guide', 'full section') RETURNING id"
        )
        await conn.execute(
            "INSERT INTO embeddings "
            "(path, chunk_index, content, embedding, chunk_hash, section_id) "
            "VALUES ('c.md', 0, 'child', $1::vector, 'hh', $2)",
            str([0.0] * 8),
            sec_id,
        )
        await conn.execute("DELETE FROM sections WHERE id=$1", sec_id)
        remaining = await conn.fetchval(
            "SELECT COUNT(*) FROM embeddings WHERE section_id=$1", sec_id
        )
    finally:
        await conn.close()
    assert remaining == 0  # CASCADE
