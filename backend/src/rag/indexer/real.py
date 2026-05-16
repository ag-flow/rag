from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol
from uuid import UUID

import asyncpg
import structlog

from rag.db.pool import WorkspacePoolRegistry
from rag.db.workspace_embeddings import delete_path, upsert_chunks
from rag.indexer.chunking import chunk_text
from rag.indexer.providers.factory import make_provider
from rag.indexer.providers.protocol import EmbeddingProvider

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


def _to_vault_ref(logical_key: str, *, vault_id: str = "rag") -> str:
    return f"${{vault://{vault_id}:{logical_key}}}"


class RealIndexer:
    """Implementation effective de `IndexerProtocol` (M4a).

    Pipeline `index_file` :
      1. Charge le contexte workspace (provider, model, api_key_ref, base_url, rag_cnx).
      2. Chunke le contenu (`chunking.chunk_text`).
      3. Resout l'API key via SecretResolver (lazy, juste avant l'embed).
      4. Embed les chunks via le provider configure.
      5. Upsert pgvector dans `rag_<workspace>.embeddings` (transaction).
      6. UPDATE `indexed_documents` (config_pool) - hash, indexer_used.

    `delete_file` :
      1. Charge le contexte workspace (pour le pool).
      2. DELETE FROM embeddings WHERE path=$1.
      3. DELETE FROM indexed_documents WHERE workspace_id=$1 AND path=$2.
    """

    def __init__(
        self,
        *,
        config_pool: asyncpg.Pool,
        pool_registry: WorkspacePoolRegistry,
        secret_resolver: _ResolverProtocol,
        provider_factory: Callable[..., EmbeddingProvider] = make_provider,
    ) -> None:
        self._config_pool = config_pool
        self._pool_registry = pool_registry
        self._secret_resolver = secret_resolver
        self._provider_factory = provider_factory

    async def index_file(
        self,
        *,
        workspace_id: UUID,
        path: str,
        content: str,
        content_hash: str,
        indexer_used: str,
    ) -> int:
        ctx = await self._load_workspace_context(workspace_id)

        chunks = chunk_text(content)
        if not chunks:
            log.info("real_indexer.empty_content_skipped", path=path)
            return 0

        api_key: str | None = None
        if ctx["api_key_ref"]:
            api_key = await self._secret_resolver.resolve_with_retry(
                _to_vault_ref(ctx["api_key_ref"]),
            )

        provider = self._provider_factory(
            provider=ctx["provider"],
            model=ctx["model"],
            api_key=api_key,
            base_url=ctx["base_url"],
        )
        embeddings = await provider.embed_texts(chunks)

        ws_pool = await self._pool_registry.get_workspace_pool(
            ctx["workspace_name"],
            ctx["rag_cnx"],
        )
        await upsert_chunks(
            ws_pool,
            path=path,
            chunks=chunks,
            embeddings=embeddings,
        )

        async with self._config_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO indexed_documents
                    (workspace_id, path, content_hash, indexer_used, indexed_at)
                VALUES ($1, $2, $3, $4, now())
                ON CONFLICT (workspace_id, path) DO UPDATE
                SET content_hash=EXCLUDED.content_hash,
                    indexer_used=EXCLUDED.indexer_used,
                    indexed_at=EXCLUDED.indexed_at
                """,
                workspace_id,
                path,
                content_hash,
                indexer_used,
            )

        log.info(
            "real_indexer.indexed",
            workspace_id=str(workspace_id),
            path=path,
            chunks=len(chunks),
        )
        return len(chunks)

    async def delete_file(self, *, workspace_id: UUID, path: str) -> None:
        ctx = await self._load_workspace_context(workspace_id)
        ws_pool = await self._pool_registry.get_workspace_pool(
            ctx["workspace_name"],
            ctx["rag_cnx"],
        )
        await delete_path(ws_pool, path)
        async with self._config_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM indexed_documents WHERE workspace_id=$1 AND path=$2",
                workspace_id,
                path,
            )
        log.info(
            "real_indexer.deleted",
            workspace_id=str(workspace_id),
            path=path,
        )

    async def _load_workspace_context(
        self,
        workspace_id: UUID,
    ) -> dict[str, Any]:
        row = await self._config_pool.fetchrow(
            """
            SELECT
                w.name AS workspace_name,
                w.rag_cnx AS rag_cnx,
                ic.provider AS provider,
                ic.model AS model,
                ic.api_key_ref AS api_key_ref,
                ic.base_url AS base_url
            FROM workspaces w
            JOIN indexer_configs ic ON ic.workspace_id = w.id
            WHERE w.id = $1
            """,
            workspace_id,
        )
        if row is None:
            raise RuntimeError(f"Workspace {workspace_id} or its indexer_config not found")
        return dict(row)
