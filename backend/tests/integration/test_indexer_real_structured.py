"""Lot 1 — RealIndexer en moteur `structured` : small-to-big (sections +
enfants), hash par chunk, et idempotence (pas de ré-embed si inchangé).
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

_DIM = 1024  # mxbai-embed-large


def _make_harpo_service() -> MagicMock:
    service = MagicMock()
    vault = MagicMock(spec=VaultSummary)
    vault.id = uuid4()
    service.get_by_name = AsyncMock(return_value=vault)
    service.write_secret = AsyncMock(return_value=None)
    service.delete_secret = AsyncMock(return_value=None)
    return service


class _CountingProvider:
    def __init__(self) -> None:
        self.embedded: list[str] = []

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.embedded.extend(texts)
        return [[0.0] * _DIM for _ in texts]


class _NullResolver:
    async def resolve_with_retry(self, ref: str) -> str:  # pragma: no cover
        raise AssertionError("resolver should not be called when api_key_ref is None")


class _StubClientProvider:
    async def get_default_vault_name(self) -> str | None:
        return None


_CONTENT = "# Guide\n\nIntro paragraph one.\n\n## Sub\n\nSub body text here."


async def _make_structured_indexer(
    migrated: asyncpg.Pool,
    admin_dsn: str,
    pg_container: str,
    name: str,
) -> tuple[RealIndexer, _CountingProvider, dict, WorkspacePoolRegistry, str]:
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
    await migrated.execute(
        "UPDATE chunking_configs SET engine='structured' WHERE workspace_id=$1",
        ws["id"],
    )
    rag_base = await migrated.fetchval(
        "SELECT rag_base FROM workspaces WHERE id=$1", ws["id"]
    )
    registry = WorkspacePoolRegistry(config_dsn=pg_container, admin_dsn=admin_dsn)
    await registry.start()
    provider = _CountingProvider()
    indexer = RealIndexer(
        config_pool=migrated,
        pool_registry=registry,
        secret_resolver=_NullResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
        provider_factory=lambda **_kw: provider,
    )
    return indexer, provider, ws, registry, rag_base


@pytest.mark.asyncio
async def test_structured_produces_sections_and_children(
    migrated: asyncpg.Pool,
    admin_dsn: str,
    pg_container: str,
) -> None:
    indexer, _provider, ws, registry, rag_base = await _make_structured_indexer(
        migrated, admin_dsn, pg_container, "ws_struct_basic"
    )
    ws_dsn = derive_workspace_dsn(admin_dsn, rag_base)
    try:
        nb = await indexer.index_file(
            workspace_id=ws["id"],
            path="t.md",
            content=_CONTENT,
            content_hash="sha256:x",
            indexer_used="ollama/mxbai-embed-large",
        )
        assert nb > 0
        conn = await asyncpg.connect(ws_dsn)
        try:
            section_keys = {
                r["section_key"]
                for r in await conn.fetch("SELECT section_key FROM sections WHERE path='t.md'")
            }
            children = await conn.fetch(
                "SELECT chunk_hash, section_id FROM embeddings WHERE path='t.md'"
            )
        finally:
            await conn.close()
        assert section_keys == {"Guide", "Guide/Sub"}
        assert all(c["chunk_hash"] is not None and c["section_id"] is not None for c in children)
    finally:
        await registry.close_all()
        await drop_workspace_database(admin_dsn, rag_base)
        await migrated.execute("DELETE FROM workspaces WHERE id=$1", ws["id"])


@pytest.mark.asyncio
async def test_reindex_unchanged_does_not_reembed(
    migrated: asyncpg.Pool,
    admin_dsn: str,
    pg_container: str,
) -> None:
    indexer, provider, ws, registry, rag_base = await _make_structured_indexer(
        migrated, admin_dsn, pg_container, "ws_struct_idem"
    )
    try:
        await indexer.index_file(
            workspace_id=ws["id"],
            path="t.md",
            content=_CONTENT,
            content_hash="sha256:x",
            indexer_used="ollama/mxbai-embed-large",
        )
        first_count = len(provider.embedded)
        assert first_count > 0
        provider.embedded.clear()
        # ré-indexation du même contenu → aucun ré-embed
        await indexer.index_file(
            workspace_id=ws["id"],
            path="t.md",
            content=_CONTENT,
            content_hash="sha256:x",
            indexer_used="ollama/mxbai-embed-large",
        )
        assert provider.embedded == []
    finally:
        await registry.close_all()
        await drop_workspace_database(admin_dsn, rag_base)
        await migrated.execute("DELETE FROM workspaces WHERE id=$1", ws["id"])
