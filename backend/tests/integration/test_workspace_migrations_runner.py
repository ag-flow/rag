from __future__ import annotations

import asyncpg
import pytest

from rag.db.workspace_migrations import apply_pending
from rag.db.workspace_schema import derive_workspace_dsn


async def _fresh_dbname(admin_dsn: str, name: str) -> None:
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


async def _drop_db(admin_dsn: str, name: str) -> None:
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_apply_pending_applies_migration_001(admin_dsn: str) -> None:
    """On a workspace DB that has `embeddings` (legacy schema, no `metadata`),
    apply_pending should add the `metadata` column and record version 1."""
    name = "rag_wsm_test_001"
    await _fresh_dbname(admin_dsn, name)
    dsn = derive_workspace_dsn(admin_dsn, name)
    try:
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
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'embeddings'"
                )
            }
            assert "metadata" in cols
        finally:
            await conn.close()
    finally:
        await _drop_db(admin_dsn, name)


@pytest.mark.asyncio
async def test_apply_pending_idempotent_on_second_run(admin_dsn: str) -> None:
    """Re-running apply_pending after success returns 0."""
    name = "rag_wsm_test_idempotent"
    await _fresh_dbname(admin_dsn, name)
    dsn = derive_workspace_dsn(admin_dsn, name)
    try:
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
    finally:
        await _drop_db(admin_dsn, name)


@pytest.mark.asyncio
async def test_apply_pending_fail_fast_when_embeddings_table_missing(
    admin_dsn: str,
) -> None:
    """If migration 001 fails (no `embeddings` table), apply_pending raises.
    workspace_schema_migrations should be created but no version inserted (transaction rollback).
    """
    name = "rag_wsm_test_failfast"
    await _fresh_dbname(admin_dsn, name)
    dsn = derive_workspace_dsn(admin_dsn, name)
    try:
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
    finally:
        await _drop_db(admin_dsn, name)
