from __future__ import annotations

import asyncpg
import pytest

from rag.db.workspace_migrations import apply_pending
from rag.db.workspace_schema import derive_workspace_dsn


@pytest.mark.asyncio
async def test_migration_001_preserves_existing_data(admin_dsn: str) -> None:
    """ALTER TABLE preserves existing rows; new column defaults to '{}'::jsonb."""
    name = "rag_wsm_001_data"
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()

    dsn = derive_workspace_dsn(admin_dsn, name)
    try:
        # Legacy table + seed data
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

        await apply_pending(dsn)

        # Verify column present, defaults to '{}', and existing data preserved
        conn = await asyncpg.connect(dsn)
        try:
            row = await conn.fetchrow(
                "SELECT content, metadata FROM embeddings WHERE path = 'a.md'"
            )
            assert row is not None
            assert row["content"] == "hello"
            # asyncpg returns jsonb as str by default — accept both
            assert row["metadata"] in ("{}", {})
        finally:
            await conn.close()
    finally:
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()
