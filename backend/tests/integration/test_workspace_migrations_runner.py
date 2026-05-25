from __future__ import annotations

import asyncpg
import pytest

from rag.db.workspace_migrations import apply_pending


@pytest.mark.asyncio
async def test_apply_pending_applies_migration_001(
    workspace_test_db: tuple[str, str],
) -> None:
    """On a workspace DB that has `embeddings` (legacy schema, no `metadata`),
    apply_pending should add the `metadata` column and record version 1."""
    _, dsn = workspace_test_db

    # Seed legacy embeddings table (sans metadata)
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

    applied = await apply_pending(dsn)
    assert applied == 1

    # Verify version + column
    conn = await asyncpg.connect(dsn)
    try:
        version = await conn.fetchval("SELECT MAX(version) FROM workspace_schema_migrations")
        assert version == 1
        cols = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'embeddings'"
            )
        }
        assert "metadata" in cols
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_apply_pending_idempotent_on_second_run(
    workspace_test_db: tuple[str, str],
) -> None:
    """Re-running apply_pending after success returns 0."""
    _, dsn = workspace_test_db

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

    first = await apply_pending(dsn)
    second = await apply_pending(dsn)
    assert first == 1
    assert second == 0


@pytest.mark.asyncio
async def test_apply_pending_fail_fast_when_embeddings_table_missing(
    workspace_test_db: tuple[str, str],
) -> None:
    """If migration 001 fails (no `embeddings` table), apply_pending raises.
    workspace_schema_migrations should be created but no version inserted (transaction rollback).
    """
    _, dsn = workspace_test_db

    with pytest.raises(asyncpg.UndefinedTableError):
        await apply_pending(dsn)

    conn = await asyncpg.connect(dsn)
    try:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'workspace_schema_migrations')"
        )
        assert exists is True
        count = await conn.fetchval("SELECT COUNT(*) FROM workspace_schema_migrations")
        assert count == 0
    finally:
        await conn.close()
