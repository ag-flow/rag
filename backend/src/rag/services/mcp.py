from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import asyncpg
import structlog
from fastapi import HTTPException, status

from rag.api.errors import WorkspaceNotFound
from rag.auth.workspace_auth import ApiKeyCache, _CacheEntry
from rag.db.pool import WorkspacePoolRegistry
from rag.db.workspace_search import vector_search
from rag.indexer.providers.factory import make_provider
from rag.indexer.providers.protocol import EmbeddingProvider
from rag.schemas.mcp import MultiWorkspaceRequest, SearchHit, SingleWorkspaceRequest
from rag.secrets.refs import build_ref
from rag.services.apikey import verify_api_key

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class McpWorkspaceRef:
    """Représentation interne d'un workspace+api_key à interroger.

    `frozen=True` : empêche `_search_one` ou `_authenticate` de muter
    accidentellement la ref entre tâches asyncio.gather concurrentes.
    """

    name: str
    api_key: str


def normalize_refs(
    req: SingleWorkspaceRequest | MultiWorkspaceRequest,
) -> list[McpWorkspaceRef]:
    """Convertit le DTO d'entrée en liste interne (ordre préservé)."""
    if isinstance(req, SingleWorkspaceRequest):
        return [McpWorkspaceRef(name=req.workspace, api_key=req.api_key)]
    return [McpWorkspaceRef(name=w.name, api_key=w.api_key) for w in req.workspaces]


async def _authenticate(
    *,
    ref: McpWorkspaceRef,
    config_pool: asyncpg.Pool,
    apikey_cache: ApiKeyCache,
) -> _CacheEntry:
    """Valide la paire (workspace_name, api_key) avec cache LRU+TTL.

    Retourne un `_CacheEntry` (workspace_id, indexer_used, inserted_at).
    - WorkspaceNotFound si workspace inconnu ou pas d'indexer_config.
    - HTTPException 401 si bcrypt verify échoue (clé invalide non mise en cache).
    """
    cached = apikey_cache.get(ref.name, ref.api_key)
    if cached is not None:
        return cached

    row = await config_pool.fetchrow(
        """
        SELECT w.id, w.api_key_hash,
               ic.provider || '/' || ic.model AS indexer_used
        FROM workspaces w
        JOIN indexer_configs ic ON ic.workspace_id = w.id
        WHERE w.name = $1
        """,
        ref.name,
    )
    if row is None:
        raise WorkspaceNotFound(ref.name)

    if not verify_api_key(ref.api_key, row["api_key_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_workspace_apikey",
        )

    entry = _CacheEntry(
        workspace_id=row["id"],
        indexer_used=row["indexer_used"],
        inserted_at=time.monotonic(),
    )
    apikey_cache.put(ref.name, ref.api_key, entry)
    return entry


async def _load_workspace_context(
    config_pool: asyncpg.Pool,
    name: str,
) -> dict[str, Any]:
    """Charge provider+model+api_key_ref+base_url+rag_cnx pour un workspace.

    Lève RuntimeError si workspace inexistant — `_authenticate` est censé
    avoir validé l'existence avant cet appel ; un None ici trahit une
    corruption d'état entre les deux SELECT.
    """
    row = await config_pool.fetchrow(
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
        WHERE w.name = $1
        """,
        name,
    )
    if row is None:
        raise RuntimeError(f"workspace {name!r} disappeared between auth and load")
    return dict(row)


# ---------------------------------------------------------------------------
# Search orchestration
# ---------------------------------------------------------------------------


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


def _to_vault_ref(logical_key: str, vault_name: str) -> str:
    """Construit une ref ``${vault://<vault_name>:<logical>}`` dynamique."""
    return build_ref(vault_name, logical_key)


@dataclass(frozen=True)
class _WorkspaceResult:
    workspace_name: str
    indexer_used: str
    hits: list[SearchHit]


async def search(
    *,
    refs: list[McpWorkspaceRef],
    query: str,
    top_k: int,
    min_score: float,
    config_pool: asyncpg.Pool,
    pool_registry: WorkspacePoolRegistry,
    apikey_cache: ApiKeyCache,
    secret_resolver: _ResolverProtocol,
    default_vault_name: str = "rag",
    provider_factory: Callable[..., EmbeddingProvider] | None = None,
) -> list[SearchHit]:
    """Orchestre la recherche MCP multi-workspace.

    Fail-fast : la première exception remontée par un workspace propage
    via `asyncio.gather` et annule les autres tasks. Aucun résultat partiel.

    `provider_factory` par défaut `None` → lookup dynamique de
    `make_provider` au runtime (permet monkey-patching côté tests
    intégration sans avoir à passer le paramètre depuis le router).
    """
    factory = provider_factory if provider_factory is not None else make_provider

    tasks = [
        _search_one(
            ref=r,
            query=query,
            top_k=top_k,
            min_score=min_score,
            config_pool=config_pool,
            pool_registry=pool_registry,
            apikey_cache=apikey_cache,
            secret_resolver=secret_resolver,
            default_vault_name=default_vault_name,
            provider_factory=factory,
        )
        for r in refs
    ]
    results = await asyncio.gather(*tasks)
    return [hit for ws_result in results for hit in ws_result.hits]


async def _search_one(
    *,
    ref: McpWorkspaceRef,
    query: str,
    top_k: int,
    min_score: float,
    config_pool: asyncpg.Pool,
    pool_registry: WorkspacePoolRegistry,
    apikey_cache: ApiKeyCache,
    secret_resolver: _ResolverProtocol,
    default_vault_name: str = "rag",
    provider_factory: Callable[..., EmbeddingProvider],
) -> _WorkspaceResult:
    auth = await _authenticate(ref=ref, config_pool=config_pool, apikey_cache=apikey_cache)
    ctx = await _load_workspace_context(config_pool, ref.name)

    api_key: str | None = None
    if ctx["api_key_ref"]:
        api_key = await secret_resolver.resolve_with_retry(
            _to_vault_ref(ctx["api_key_ref"], default_vault_name)
        )

    provider = provider_factory(
        provider=ctx["provider"],
        model=ctx["model"],
        api_key=api_key,
        base_url=ctx["base_url"],
    )
    query_vec = await provider.embed_query(query)

    ws_pool = await pool_registry.get_workspace_pool(ref.name, ctx["rag_cnx"])
    hits = await vector_search(
        ws_pool,
        query_vec=query_vec,
        top_k=top_k,
        min_score=min_score,
        workspace_name=ref.name,
        indexer_used=auth.indexer_used,
    )
    log.info(
        "mcp.search.workspace_done",
        workspace=ref.name,
        hits=len(hits),
        indexer=auth.indexer_used,
    )
    return _WorkspaceResult(
        workspace_name=ref.name,
        indexer_used=auth.indexer_used,
        hits=hits,
    )
