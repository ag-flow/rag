from __future__ import annotations

import asyncpg
import pytest

from rag.db.workspace_migrations import apply_pending
from rag.db.workspace_structured import (
    ChildRow,
    ParentRow,
    delete_sections_for_path,
    load_existing_chunk_hashes,
    upsert_structured,
)


async def _prepare(dsn: str) -> None:
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
    finally:
        await conn.close()
    await apply_pending(dsn)  # 001 (metadata) + 002 (sections + chunk_hash)


def _vec() -> list[float]:
    return [0.1] * 8


def _child(h: str, idx: int, parent: str = "Guide", *, embed: bool = True) -> ChildRow:
    return ChildRow(
        chunk_hash=h,
        embed_text=f"Guide\n\n{h}",
        parent_key=parent,
        chunk_index=idx,
        metadata={"section_title": "Guide"},
        embedding=_vec() if embed else None,
    )


@pytest.mark.asyncio
async def test_insert_parent_and_children(workspace_test_db: tuple[str, str]) -> None:
    _, dsn = workspace_test_db
    await _prepare(dsn)
    pool = await asyncpg.create_pool(dsn)
    try:
        result = await upsert_structured(
            pool,
            path="a.md",
            parents=[ParentRow("Guide", "# Guide\n\nbody")],
            children=[_child("sha256:h1", 0), _child("sha256:h2", 1)],
        )
        async with pool.acquire() as conn:
            n_sections = await conn.fetchval("SELECT COUNT(*) FROM sections WHERE path='a.md'")
            rows = await conn.fetch(
                "SELECT chunk_hash, section_id FROM embeddings WHERE path='a.md' "
                "ORDER BY chunk_index"
            )
    finally:
        await pool.close()

    assert result["inserted"] == 2
    assert n_sections == 1
    assert [r["chunk_hash"] for r in rows] == ["sha256:h1", "sha256:h2"]
    assert all(r["section_id"] is not None for r in rows)


@pytest.mark.asyncio
async def test_reindex_unchanged_is_idempotent(workspace_test_db: tuple[str, str]) -> None:
    _, dsn = workspace_test_db
    await _prepare(dsn)
    pool = await asyncpg.create_pool(dsn)
    try:
        await upsert_structured(
            pool,
            path="a.md",
            parents=[ParentRow("Guide", "# Guide\n\nbody")],
            children=[_child("sha256:h1", 0)],
        )
        existing = await load_existing_chunk_hashes(pool, "a.md")
        assert existing == {"sha256:h1"}
        # ré-indexation inchangée : enfant conservé (embedding None), aucun insert
        result = await upsert_structured(
            pool,
            path="a.md",
            parents=[ParentRow("Guide", "# Guide\n\nbody")],
            children=[_child("sha256:h1", 0, embed=False)],
        )
        async with pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM embeddings WHERE path='a.md'")
    finally:
        await pool.close()

    assert result["inserted"] == 0
    assert result["kept"] == 1
    assert count == 1


@pytest.mark.asyncio
async def test_partial_edit_only_changes_modified(workspace_test_db: tuple[str, str]) -> None:
    _, dsn = workspace_test_db
    await _prepare(dsn)
    pool = await asyncpg.create_pool(dsn)
    try:
        await upsert_structured(
            pool,
            path="a.md",
            parents=[ParentRow("Guide", "v1")],
            children=[_child("sha256:h1", 0), _child("sha256:h2", 1)],
        )
        # h2 supprimé, h3 ajouté, h1 conservé
        result = await upsert_structured(
            pool,
            path="a.md",
            parents=[ParentRow("Guide", "v2")],
            children=[_child("sha256:h1", 0, embed=False), _child("sha256:h3", 1)],
        )
        async with pool.acquire() as conn:
            hashes = {
                r["chunk_hash"]
                for r in await conn.fetch("SELECT chunk_hash FROM embeddings WHERE path='a.md'")
            }
            section_content = await conn.fetchval(
                "SELECT content FROM sections WHERE path='a.md' AND section_key='Guide'"
            )
    finally:
        await pool.close()

    assert result == {"inserted": 1, "kept": 1, "deleted": 1, "sections": 1}
    assert hashes == {"sha256:h1", "sha256:h3"}
    assert section_content == "v2"  # parent mis à jour, id stable


@pytest.mark.asyncio
async def test_delete_sections_for_path_removes_parents_and_children(
    workspace_test_db: tuple[str, str],
) -> None:
    """Fix : delete_file ne doit pas laisser de sections orphelines. La purge
    des sections cascade sur leurs enfants embeddings."""
    _, dsn = workspace_test_db
    await _prepare(dsn)
    pool = await asyncpg.create_pool(dsn)
    try:
        await upsert_structured(
            pool,
            path="a.md",
            parents=[ParentRow("Guide", "# Guide\n\nbody")],
            children=[_child("sha256:h1", 0)],
        )
        removed = await delete_sections_for_path(pool, "a.md")
        async with pool.acquire() as conn:
            n_sections = await conn.fetchval("SELECT COUNT(*) FROM sections WHERE path='a.md'")
            n_children = await conn.fetchval("SELECT COUNT(*) FROM embeddings WHERE path='a.md'")
    finally:
        await pool.close()
    assert removed == 1
    assert n_sections == 0
    assert n_children == 0  # cascade FK section_id


@pytest.mark.asyncio
async def test_structured_replaces_legacy_rows(workspace_test_db: tuple[str, str]) -> None:
    _, dsn = workspace_test_db
    await _prepare(dsn)
    pool = await asyncpg.create_pool(dsn)
    try:
        async with pool.acquire() as conn:
            from pgvector.asyncpg import register_vector

            await register_vector(conn)
            await conn.execute(
                "INSERT INTO embeddings (path, chunk_index, content, embedding) "
                "VALUES ('a.md', 0, 'legacy', $1)",
                _vec(),
            )
        await upsert_structured(
            pool,
            path="a.md",
            parents=[ParentRow("Guide", "body")],
            children=[_child("sha256:h1", 0)],
        )
        async with pool.acquire() as conn:
            contents = [
                r["content"]
                for r in await conn.fetch("SELECT content FROM embeddings WHERE path='a.md'")
            ]
    finally:
        await pool.close()

    assert contents == ["Guide\n\nsha256:h1"]  # ligne legacy purgée
