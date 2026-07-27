from __future__ import annotations

import asyncpg
import pytest

from rag.db.workspace_migrations import apply_pending
from rag.db.workspace_migrations.runner import _list_versions

# Dérivés du répertoire versions/ (source de vérité) pour que les tests ne
# dérivent pas à chaque nouvelle migration workspace. L'import du helper privé
# `_list_versions` est assumé (même choix que `_admin_dsn` dans conftest).
_ALL_VERSIONS = _list_versions()
_TOTAL = len(_ALL_VERSIONS)
_LATEST = max(v for v, _ in _ALL_VERSIONS)


async def _seed_legacy_embeddings(dsn: str) -> None:
    """Table embeddings 'legacy' (sans metadata) : point de départ des migrations."""
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


@pytest.mark.asyncio
async def test_apply_pending_applies_all_versions(
    workspace_test_db: tuple[str, str],
) -> None:
    """Sur une base workspace 'legacy' (embeddings sans `metadata`), apply_pending
    applique toutes les migrations workspace et enregistre la dernière version."""
    _, dsn = workspace_test_db
    await _seed_legacy_embeddings(dsn)

    applied = await apply_pending(dsn)
    assert applied == _TOTAL

    conn = await asyncpg.connect(dsn)
    try:
        version = await conn.fetchval("SELECT MAX(version) FROM workspace_schema_migrations")
        assert version == _LATEST
        cols = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'embeddings'"
            )
        }
        assert "metadata" in cols  # apport de la migration 001
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_apply_pending_idempotent_on_second_run(
    workspace_test_db: tuple[str, str],
) -> None:
    """Re-running apply_pending after success returns 0."""
    _, dsn = workspace_test_db
    await _seed_legacy_embeddings(dsn)

    first = await apply_pending(dsn)
    second = await apply_pending(dsn)
    assert first == _TOTAL
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
