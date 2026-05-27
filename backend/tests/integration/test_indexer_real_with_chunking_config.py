"""Test M9-T6 : RealIndexer lit la chunking_config et applique les paramètres
(max_chars/min_chars/overlap_chars) pour découper le contenu.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncpg
import pytest

from rag.db.pool import WorkspacePoolRegistry
from rag.db.workspace_schema import derive_workspace_dsn, drop_workspace_database
from rag.indexer.real import RealIndexer
from rag.schemas.admin import IndexerSpec, WorkspaceCreateRequest
from rag.schemas.harpocrate_vaults import VaultSummary
from rag.services.workspaces import create_workspace


def _make_harpo_service() -> MagicMock:
    service = MagicMock()
    vault = MagicMock(spec=VaultSummary)
    vault.id = uuid4()
    service.get_by_name = AsyncMock(return_value=vault)
    service.write_secret = AsyncMock(return_value=None)
    service.delete_secret = AsyncMock(return_value=None)
    return service


class _StubProvider:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


class _NullResolver:
    async def resolve_with_retry(self, ref: str) -> str:  # pragma: no cover
        raise AssertionError("resolver should not be called when api_key_ref is None")


class _StubClientProvider:
    async def get_default_vault_name(self) -> str | None:
        return None


@pytest.mark.asyncio
async def test_real_indexer_respects_chunking_config_max_chars(
    migrated: asyncpg.Pool,
    admin_dsn: str,
    pg_container: str,
) -> None:
    """RealIndexer lit chunking_config et applique max_chars pour produire plusieurs chunks."""
    name = "ws_realidx_chunk"
    req = WorkspaceCreateRequest(
        name=name,
        api_key_vault="rag",
        indexer=IndexerSpec(
            provider="ollama",
            model="mxbai-embed-large",
            api_key_ref=None,
            base_url="http://stub:11434",
        ),
    )
    ws = await create_workspace(
        request=req,
        config_pool=migrated,
        admin_dsn=admin_dsn,
        resolver=_NullResolver(),  # type: ignore[arg-type]
        harpocrate_vaults_service=_make_harpo_service(),
    )
    rag_base = await migrated.fetchval(
        "SELECT rag_base FROM workspaces WHERE id = $1",
        ws["id"],
    )
    ws_dsn = derive_workspace_dsn(admin_dsn, rag_base)

    registry: WorkspacePoolRegistry | None = None
    try:
        # Force chunking_config petite pour garantir splits multiples.
        await migrated.execute(
            "UPDATE chunking_configs SET max_chars=500, min_chars=50, overlap_chars=50 "
            "WHERE workspace_id = $1",
            ws["id"],
        )

        # Workaround test : recrée embeddings avec dim=8 pour matcher le stub.
        # create_workspace l'a créée avec dim=1024 (mxbai-embed-large) ; le stub
        # renvoie des vecteurs 8-dim pour rester lisible. Pas de chemin de prod ici —
        # on shortcut volontairement la cohérence dim modèle ↔ table.
        conn = await asyncpg.connect(ws_dsn)
        try:
            await conn.execute("DROP TABLE IF EXISTS embeddings CASCADE")
            await conn.execute(
                "CREATE TABLE embeddings ("
                "id SERIAL PRIMARY KEY, path TEXT NOT NULL, "
                "chunk_index INT NOT NULL, content TEXT NOT NULL, "
                "embedding vector(8) NOT NULL, "
                "metadata JSONB NOT NULL DEFAULT '{}'::jsonb, "
                "indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "UNIQUE (path, chunk_index))"
            )
        finally:
            await conn.close()

        registry = WorkspacePoolRegistry(
            config_dsn=pg_container,
            admin_dsn=admin_dsn,
        )
        await registry.start()

        indexer = RealIndexer(
            config_pool=migrated,
            pool_registry=registry,
            secret_resolver=_NullResolver(),  # type: ignore[arg-type]
            client_provider=_StubClientProvider(),  # type: ignore[arg-type]
            provider_factory=lambda **_kw: _StubProvider(),
        )

        # 1500-char text → avec max_chars=500 doit produire >= 2 chunks.
        content = "Phrase courte. " * 100
        nb = await indexer.index_file(
            workspace_id=ws["id"],
            path="t.md",
            content=content,
            content_hash="sha256:x",
            indexer_used="ollama/mxbai-embed-large",
        )
        assert nb >= 2

        # metadata doit être vide pour chaque chunk (ParagraphChunker).
        conn = await asyncpg.connect(ws_dsn)
        try:
            rows = await conn.fetch(
                "SELECT chunk_index, metadata FROM embeddings WHERE path = 't.md'"
            )
            assert len(rows) == nb
            for r in rows:
                # asyncpg renvoie jsonb en str par défaut
                assert r["metadata"] in ("{}", {})
        finally:
            await conn.close()
    finally:
        if registry is not None:
            await registry.close_all()
        await drop_workspace_database(admin_dsn, rag_base)
        await migrated.execute("DELETE FROM workspaces WHERE id = $1", ws["id"])
