"""Table workspace `source_documents` (migration ws 006) : upsert/list/delete
et invariant clé — le contenu SURVIT au reset de schéma du changement
d'indexeur (reset_workspace_schema ne droppe pas la table, la migration
rejouée est un no-op)."""

from __future__ import annotations

import asyncpg
import pytest

from rag.db.source_documents import (
    delete_source_document,
    list_source_documents,
    upsert_source_document,
)
from rag.db.workspace_schema import provision_workspace_schema, reset_workspace_schema


async def _insert_doc(pool: asyncpg.Pool, path: str = "docs/a.md") -> None:
    await upsert_source_document(
        pool,
        path=path,
        content="contenu initial",
        content_hash="sha256:aaa",
        title="Titre",
        source_url="https://doc/a",
    )


@pytest.mark.asyncio
async def test_upsert_list_delete_roundtrip(workspace_test_db: tuple[str, str]) -> None:
    _, dsn = workspace_test_db
    await provision_workspace_schema(dsn, dimension=8)
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    try:
        await _insert_doc(pool)
        await upsert_source_document(
            pool,
            path="docs/a.md",
            content="contenu mis à jour",
            content_hash="sha256:bbb",
            title="Titre v2",
            source_url=None,
        )
        rows = await list_source_documents(pool)
        assert len(rows) == 1
        assert rows[0]["content"] == "contenu mis à jour"
        assert rows[0]["content_hash"] == "sha256:bbb"
        # source_url absent à l'update → l'ancienne valeur est conservée
        assert rows[0]["source_url"] == "https://doc/a"

        await delete_source_document(pool, "docs/a.md")
        assert await list_source_documents(pool) == []
        # idempotent
        await delete_source_document(pool, "docs/a.md")
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_content_survives_indexer_reset(workspace_test_db: tuple[str, str]) -> None:
    """Changement d'indexeur = reset_workspace_schema + reprovision (autre
    dimension) : les sources stockées doivent rester — c'est la matière
    première du job de réindexation qui suit."""
    _, dsn = workspace_test_db
    await provision_workspace_schema(dsn, dimension=8)
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    try:
        await _insert_doc(pool)
    finally:
        await pool.close()

    await reset_workspace_schema(dsn)
    await provision_workspace_schema(dsn, dimension=16)

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    try:
        rows = await list_source_documents(pool)
        assert [r["path"] for r in rows] == ["docs/a.md"]
        assert rows[0]["content"] == "contenu initial"
    finally:
        await pool.close()
