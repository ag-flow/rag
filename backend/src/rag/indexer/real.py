from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any, Protocol
from uuid import UUID

import asyncpg
import structlog

from rag.db.path_strategies import get_strategy
from rag.db.pool import WorkspacePoolRegistry
from rag.db.workspace_embeddings import delete_path, upsert_chunks
from rag.indexer.chunking import Chunk, make_chunker
from rag.indexer.providers.factory import make_provider
from rag.indexer.providers.protocol import EmbeddingProvider
from rag.secrets.refs import build_ref, is_vault_ref

log = structlog.get_logger(__name__)

_API_KEY_CACHE_TTL = 300  # secondes


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


class _ClientProviderProtocol(Protocol):
    async def get_default_vault_name(self) -> str | None: ...


def _to_vault_ref(logical_key: str, vault_name: str) -> str:
    """Construit une ref ``${vault://<vault_name>:<logical>}`` dynamique."""
    return build_ref(vault_name, logical_key)


class _NoDefaultVaultError(RuntimeError):
    """Levée quand aucun coffre par défaut n'est configuré alors qu'un
    secret est requis pour indexer ce workspace."""

    def __init__(self) -> None:
        super().__init__("no default Harpocrate vault configured")


class RealIndexer:
    """Implementation effective de `IndexerProtocol` (M4a).

    Pipeline `index_file` :
      1. Charge le contexte workspace (provider, model, api_key_ref, base_url,
         rag_cnx, + chunking_config).
      2. Chunke le contenu via le chunker construit par `make_chunker` selon la
         `chunking_config` du workspace.
      3. Resout l'API key via SecretResolver (lazy, juste avant l'embed).
      4. Embed les contenus des chunks via le provider configure.
      5. Upsert pgvector dans `rag_<workspace>.embeddings` (content + embedding
         + metadata, transaction).
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
        client_provider: _ClientProviderProtocol,
        provider_factory: Callable[..., EmbeddingProvider] = make_provider,
    ) -> None:
        self._config_pool = config_pool
        self._pool_registry = pool_registry
        self._secret_resolver = secret_resolver
        self._client_provider = client_provider
        self._provider_factory = provider_factory
        self._api_key_cache: dict[str, tuple[str, float]] = {}  # ref → (value, expires_at)

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

        chunker = make_chunker(
            strategy=ctx["chunking_strategy"],
            max_chars=ctx["chunking_max_chars"],
            min_chars=ctx["chunking_min_chars"],
            overlap_chars=ctx["chunking_overlap_chars"],
            extras=ctx["chunking_extras"],
        )
        chunks: list[Chunk] = chunker.chunk(content)
        if not chunks:
            log.info("real_indexer.empty_content_skipped", path=path)
            return 0

        api_key: str | None = None
        if ctx["api_key_ref"]:
            ref = ctx["api_key_ref"]
            if not is_vault_ref(ref):
                default_vault_name = await self._client_provider.get_default_vault_name()
                if default_vault_name is None:
                    log.warning(
                        "real_indexer.no_default_vault",
                        workspace_id=str(workspace_id),
                        path=path,
                    )
                    raise _NoDefaultVaultError()
                ref = _to_vault_ref(ref, default_vault_name)
            cached = self._api_key_cache.get(ref)
            if cached is None or time.monotonic() > cached[1]:
                api_key = await self._secret_resolver.resolve_with_retry(ref)
                self._api_key_cache[ref] = (api_key, time.monotonic() + _API_KEY_CACHE_TTL)
                log.debug("real_indexer.api_key_cache_miss", ref=ref)
            else:
                api_key = cached[0]

        provider = self._provider_factory(
            service=ctx["service"],
            provider=ctx["provider"],
            model=ctx["model"],
            api_key=api_key,
            base_url=ctx["base_url"],
        )
        embeddings = await provider.embed_texts([c.content for c in chunks])

        ws_pool = await self._pool_registry.get_workspace_pool(
            ctx["workspace_name"],
            ctx["rag_cnx"],
        )
        strategy = await get_strategy(self._config_pool, workspace_id, path)
        await upsert_chunks(
            ws_pool,
            path=path,
            chunks=chunks,
            embeddings=embeddings,
            strategy=strategy,
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
            chunking_strategy=ctx["chunking_strategy"],
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
                ic.base_url AS base_url,
                md.service AS service,
                cc.strategy AS chunking_strategy,
                cc.max_chars AS chunking_max_chars,
                cc.min_chars AS chunking_min_chars,
                cc.overlap_chars AS chunking_overlap_chars,
                cc.extras AS chunking_extras
            FROM workspaces w
            JOIN indexer_configs ic ON ic.workspace_id = w.id
            JOIN model_dimensions md ON md.provider = ic.provider AND md.model = ic.model
            JOIN chunking_configs cc ON cc.workspace_id = w.id
            WHERE w.id = $1
            """,
            workspace_id,
        )
        if row is None:
            raise RuntimeError(f"Workspace {workspace_id} or its indexer/chunking config not found")
        ctx = dict(row)
        # extras peut revenir en str selon codec asyncpg
        if isinstance(ctx["chunking_extras"], str):
            ctx["chunking_extras"] = json.loads(ctx["chunking_extras"])
        return ctx
