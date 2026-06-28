from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol
from uuid import UUID

import asyncpg
import structlog

from rag.db.path_strategies import get_strategy
from rag.db.pool import WorkspacePoolRegistry
from rag.db.workspace_embeddings import delete_path, upsert_chunks
from rag.db.workspace_structured import (
    ChildRow,
    ParentRow,
    delete_sections_for_path,
    load_existing_chunk_hashes,
    plan_children,
    upsert_structured,
)
from rag.indexer.chunking import Chunk, make_chunker
from rag.indexer.chunking.hashing import compute_chunk_hash
from rag.indexer.chunking.languages import language_for_path
from rag.indexer.chunking.resolution import resolve_strategy_name
from rag.indexer.chunking.structured_factory import make_structured_chunker
from rag.indexer.chunking.tokens import HeuristicTokenEstimator
from rag.indexer.providers.factory import make_provider
from rag.indexer.providers.protocol import EmbeddingProvider
from rag.secrets.refs import build_ref, is_vault_ref
from rag.services.chunking_routing import load_routing, load_strategy

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

    Deux pipelines coexistent derrière le flag `chunking_configs.engine` :

    - ``legacy``     : découpe plate char-based (`make_chunker`), upsert
      `embeddings` en replace/append. Comportement historique inchangé.
    - ``structured`` : routage par type → stratégie nommée, small-to-big
      (sections + enfants), bornes en tokens, breadcrumb, et upsert en diff
      par `chunk_hash` (réutilise les chunks inchangés). Cf. ADR 0001.
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
        title: str | None = None,
        strategy_override: str | None = None,
        extra_metadata: Mapping[str, Any] | None = None,
    ) -> int:
        ctx = await self._load_workspace_context(workspace_id)
        if ctx["chunking_engine"] == "structured":
            n_chunks = await self._index_structured(
                workspace_id=workspace_id,
                path=path,
                content=content,
                ctx=ctx,
                strategy_override=strategy_override,
                extra_metadata=extra_metadata or {},
            )
        else:
            n_chunks = await self._index_legacy(
                workspace_id=workspace_id,
                path=path,
                content=content,
                ctx=ctx,
                extra_metadata=extra_metadata or {},
            )
        if n_chunks == 0:
            log.info("real_indexer.empty_content_skipped", path=path)
            return 0
        await self._record_indexed_document(workspace_id, path, content_hash, indexer_used, title)
        return n_chunks

    async def _index_legacy(
        self,
        *,
        workspace_id: UUID,
        path: str,
        content: str,
        ctx: dict[str, Any],
        extra_metadata: Mapping[str, Any] = {},
    ) -> int:
        chunker = make_chunker(
            strategy=ctx["chunking_strategy"],
            max_chars=ctx["chunking_max_chars"],
            min_chars=ctx["chunking_min_chars"],
            overlap_chars=ctx["chunking_overlap_chars"],
            extras=ctx["chunking_extras"],
        )
        chunks: list[Chunk] = chunker.chunk(content)
        if extra_metadata:
            import dataclasses

            chunks = [
                dataclasses.replace(c, metadata={**extra_metadata, **dict(c.metadata)})
                for c in chunks
            ]
        if not chunks:
            return 0

        api_key = await self._resolve_api_key(ctx, workspace_id, path)
        provider = self._build_provider(ctx, api_key)
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
        log.info(
            "real_indexer.indexed",
            workspace_id=str(workspace_id),
            path=path,
            chunks=len(chunks),
            chunking_strategy=ctx["chunking_strategy"],
            engine="legacy",
        )
        return len(chunks)

    async def _index_structured(
        self,
        *,
        workspace_id: UUID,
        path: str,
        content: str,
        ctx: dict[str, Any],
        strategy_override: str | None,
        extra_metadata: Mapping[str, Any] = {},
    ) -> int:
        routing = await load_routing(self._config_pool, workspace_id)
        strategy_name = resolve_strategy_name(
            path=path, override=strategy_override, routing=routing
        )
        algo, params = await load_strategy(self._config_pool, workspace_id, strategy_name)
        estimator = HeuristicTokenEstimator(char_ratio=float(ctx["token_char_ratio"]))
        language = language_for_path(path) if algo in ("code", "data") else None
        chunker = make_structured_chunker(
            algo=algo,
            params=params,
            estimator=estimator,
            provider_max_input_tokens=int(ctx["max_input_tokens"]),
            language=language,
        )
        doc = chunker.chunk(content)
        ordered = _dedupe_by_hash(doc.children)
        if not ordered:
            return 0

        ws_pool = await self._pool_registry.get_workspace_pool(
            ctx["workspace_name"],
            ctx["rag_cnx"],
        )
        existing = await load_existing_chunk_hashes(ws_pool, path)
        plan = plan_children(existing, [h for h, _ in ordered])
        new_set = set(plan.new_hashes)

        to_embed = [(h, child) for h, child in ordered if h in new_set]
        api_key = await self._resolve_api_key(ctx, workspace_id, path)
        provider = self._build_provider(ctx, api_key)
        embeddings = (
            await provider.embed_texts([c.embed_text for _, c in to_embed]) if to_embed else []
        )
        emb_by_hash = {h: emb for (h, _), emb in zip(to_embed, embeddings, strict=True)}

        child_rows = [
            ChildRow(
                chunk_hash=h,
                embed_text=child.embed_text,
                parent_key=child.parent_key,
                chunk_index=idx,
                metadata=(
                    {**extra_metadata, **dict(child.metadata)} if extra_metadata else child.metadata
                ),
                embedding=emb_by_hash.get(h),
            )
            for idx, (h, child) in enumerate(ordered)
        ]
        parent_rows = [
            ParentRow(
                section_key=p.section_key,
                content=p.content,
                metadata={**extra_metadata, **dict(p.metadata)} if extra_metadata else p.metadata,
                section_index=idx,
            )
            for idx, p in enumerate(doc.parents)
        ]
        result = await upsert_structured(
            ws_pool, path=path, parents=parent_rows, children=child_rows
        )
        log.info(
            "real_indexer.indexed",
            workspace_id=str(workspace_id),
            path=path,
            engine="structured",
            strategy=strategy_name,
            **result,
        )
        return len(child_rows)

    async def _resolve_api_key(
        self,
        ctx: dict[str, Any],
        workspace_id: UUID,
        path: str,
    ) -> str | None:
        if not ctx["api_key_ref"]:
            return None
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
            return api_key
        return cached[0]

    def _build_provider(self, ctx: dict[str, Any], api_key: str | None) -> EmbeddingProvider:
        return self._provider_factory(
            service=ctx["service"],
            provider=ctx["provider"],
            model=ctx["model"],
            api_key=api_key,
            base_url=ctx["base_url"],
        )

    async def _record_indexed_document(
        self,
        workspace_id: UUID,
        path: str,
        content_hash: str,
        indexer_used: str,
        title: str | None = None,
    ) -> None:
        async with self._config_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO indexed_documents
                    (workspace_id, path, content_hash, indexer_used, title, indexed_at)
                VALUES ($1, $2, $3, $4, $5, now())
                ON CONFLICT (workspace_id, path) DO UPDATE
                SET content_hash=EXCLUDED.content_hash,
                    indexer_used=EXCLUDED.indexer_used,
                    title=EXCLUDED.title,
                    indexed_at=EXCLUDED.indexed_at
                """,
                workspace_id,
                path,
                content_hash,
                indexer_used,
                title,
            )

    async def delete_file(self, *, workspace_id: UUID, path: str) -> None:
        ctx = await self._load_workspace_context(workspace_id)
        ws_pool = await self._pool_registry.get_workspace_pool(
            ctx["workspace_name"],
            ctx["rag_cnx"],
        )
        await delete_path(ws_pool, path)
        await delete_sections_for_path(ws_pool, path)
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
                md.max_input_tokens AS max_input_tokens,
                md.token_char_ratio AS token_char_ratio,
                cc.engine AS chunking_engine,
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


def _dedupe_by_hash(children: list[Any]) -> list[tuple[str, Any]]:
    """(hash, child) en ordre doc, dédoublonné par hash (1ʳᵉ occurrence)."""
    seen: set[str] = set()
    ordered: list[tuple[str, Any]] = []
    for child in children:
        h = compute_chunk_hash(child.embed_text)
        if h in seen:
            continue
        seen.add(h)
        ordered.append((h, child))
    return ordered
