from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from secrets import compare_digest
from typing import Any, Protocol

import asyncpg
import structlog
from fastapi import HTTPException, status

from rag.api.errors import HarpocrateUnreachableForApikey, VaultUnreachable, WorkspaceNotFound
from rag.auth.workspace_auth import ApiKeyCache
from rag.db.pool import WorkspacePoolRegistry
from rag.db.workspace_search import hybrid_search, vector_search
from rag.indexer.providers.factory import make_provider
from rag.indexer.providers.protocol import EmbeddingProvider
from rag.rerank.protocol import RerankProvider
from rag.rerank.providers.factory import make_rerank_provider as _make_rerank_default
from rag.schemas.mcp import MultiWorkspaceRequest, SearchHit, SingleWorkspaceRequest
from rag.secrets.refs import build_ref

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class _CacheEntry:
    """Résultat d'authentification d'un workspace (workspace_id + indexer_used)."""

    workspace_id: object  # UUID asyncpg
    indexer_used: str
    inserted_at: float


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


class _SecretResolverProtocolForAuth(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


async def _authenticate(
    *,
    ref: McpWorkspaceRef,
    config_pool: asyncpg.Pool,
    apikey_cache: ApiKeyCache,
    secret_resolver: _SecretResolverProtocolForAuth,
) -> _CacheEntry:
    """Valide la paire (workspace_name, api_key) via fingerprint+cache+Harpocrate.

    Lookup O(1) par fingerprint SHA-256 → résolution via cache process-lifetime
    (puis Harpocrate sur miss) → comparaison timing-safe.

    Retourne un `_CacheEntry` (workspace_id, indexer_used, inserted_at).
    - WorkspaceNotFound si workspace inconnu ou pas d'indexer_config.
    - HTTPException 401 si la clé ne correspond pas.
    - HarpocrateUnreachableForApikey si Harpocrate inaccessible sur cache miss.
    """
    fingerprint = sha256(ref.api_key.encode("utf-8")).hexdigest()

    row = await config_pool.fetchrow(
        """
        SELECT w.id,
               k.api_key_ref,
               ic.provider || '/' || ic.model AS indexer_used
        FROM workspaces w
        JOIN workspace_api_keys k ON k.workspace_id = w.id
        JOIN indexer_configs ic ON ic.workspace_id = w.id
        WHERE w.name = $1
          AND k.fingerprint = $2
          AND k.revoked_at IS NULL
          AND (k.rotated_at IS NULL OR k.rotated_at > now() - interval '72 hours')
        """,
        ref.name,
        fingerprint,
    )
    if row is None:
        # Workspace inconnu OU fingerprint ne matche pas → 401 uniforme.
        # On fait un second SELECT pour distinguer WorkspaceNotFound de 401.
        exists = await config_pool.fetchval(
            "SELECT 1 FROM workspaces WHERE name = $1", ref.name
        )
        if exists is None:
            raise WorkspaceNotFound(ref.name)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_workspace_apikey",
        )

    api_key_ref: str = row["api_key_ref"]
    cached = apikey_cache.get(api_key_ref)
    if cached is None:
        try:
            cached = await secret_resolver.resolve_with_retry(api_key_ref)
        except VaultUnreachable as e:
            raise HarpocrateUnreachableForApikey() from e
        apikey_cache.put(api_key_ref, cached)

    if not compare_digest(cached, ref.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_workspace_apikey",
        )

    return _CacheEntry(
        workspace_id=row["id"],
        indexer_used=row["indexer_used"],
        inserted_at=time.monotonic(),
    )


async def _load_workspace_context(
    config_pool: asyncpg.Pool,
    name: str,
) -> dict[str, Any]:
    """Charge provider+model+api_key_ref+base_url+rag_cnx pour un workspace.

    Charge aussi la config rerank (LEFT JOIN). Si rerank_configs n'a pas de row,
    le dict retourné contient `rerank=None`. Sinon contient
    `rerank={provider, model, api_key_ref, base_url, top_k_pre_rerank}`.

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
            ic.base_url AS base_url,
            md.service AS service,
            rc.provider AS rerank_provider,
            rc.model AS rerank_model,
            rc.api_key_ref AS rerank_api_key_ref,
            rc.base_url AS rerank_base_url,
            rc.top_k_pre_rerank AS rerank_top_k_pre_rerank
        FROM workspaces w
        JOIN indexer_configs ic ON ic.workspace_id = w.id
        JOIN model_dimensions md ON md.provider = ic.provider AND md.model = ic.model
        LEFT JOIN rerank_configs rc ON rc.workspace_id = w.id
        WHERE w.name = $1
        """,
        name,
    )
    if row is None:
        raise RuntimeError(f"workspace {name!r} disappeared between auth and load")
    ctx = dict(row)
    if ctx.get("rerank_provider") is not None:
        ctx["rerank"] = {
            "provider": ctx["rerank_provider"],
            "model": ctx["rerank_model"],
            "api_key_ref": ctx["rerank_api_key_ref"],
            "base_url": ctx["rerank_base_url"],
            "top_k_pre_rerank": ctx["rerank_top_k_pre_rerank"],
        }
    else:
        ctx["rerank"] = None
    # Cleanup : retirer les clés intermédiaires
    for k in ("rerank_provider", "rerank_model", "rerank_api_key_ref",
              "rerank_base_url", "rerank_top_k_pre_rerank"):
        ctx.pop(k, None)
    return ctx


async def _load_hybrid_config(
    config_pool: asyncpg.Pool,
    workspace_id: object,
) -> dict[str, object] | None:
    """Charge la config hybride depuis hybrid_configs. None = vectoriel pur."""
    row = await config_pool.fetchrow(
        "SELECT enabled, rrf_k, fts_config FROM hybrid_configs WHERE workspace_id = $1",
        workspace_id,
    )
    if row is None:
        return None
    return {"enabled": row["enabled"], "rrf_k": row["rrf_k"], "fts_config": row["fts_config"]}


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
    rerank_factory: Callable[..., RerankProvider] | None = None,
) -> list[SearchHit]:
    """Orchestre la recherche MCP multi-workspace.

    Fail-fast : la première exception remontée par un workspace propage
    via `asyncio.gather` et annule les autres tasks. Aucun résultat partiel.

    `provider_factory` par défaut `None` → lookup dynamique de
    `make_provider` au runtime (permet monkey-patching côté tests
    intégration sans avoir à passer le paramètre depuis le router).

    `rerank_factory` par défaut `None` → `_make_rerank_default` (opt-in :
    workspaces sans rerank_configs row = comportement inchangé).
    """
    factory = provider_factory if provider_factory is not None else make_provider
    rfactory = rerank_factory if rerank_factory is not None else _make_rerank_default

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
            rerank_factory=rfactory,
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
    default_vault_name: str,
    provider_factory: Callable[..., EmbeddingProvider],
    rerank_factory: Callable[..., RerankProvider],
) -> _WorkspaceResult:
    auth = await _authenticate(
        ref=ref,
        config_pool=config_pool,
        apikey_cache=apikey_cache,
        secret_resolver=secret_resolver,
    )
    ctx = await _load_workspace_context(config_pool, ref.name)

    api_key: str | None = None
    if ctx["api_key_ref"]:
        api_key = await secret_resolver.resolve_with_retry(
            _to_vault_ref(ctx["api_key_ref"], default_vault_name)
        )

    provider = provider_factory(
        service=ctx["service"],
        provider=ctx["provider"],
        model=ctx["model"],
        api_key=api_key,
        base_url=ctx["base_url"],
    )
    query_vec = await provider.embed_query(query)

    rerank_cfg = ctx.get("rerank")
    pre_top_k = max(top_k, rerank_cfg["top_k_pre_rerank"]) if rerank_cfg else top_k

    hybrid_cfg = await _load_hybrid_config(config_pool, auth.workspace_id)
    ws_pool = await pool_registry.get_workspace_pool(ref.name, ctx["rag_cnx"])

    if hybrid_cfg and hybrid_cfg["enabled"]:
        hits = await hybrid_search(
            ws_pool,
            query_vec=query_vec,
            query=query,
            top_k=pre_top_k,
            min_score=min_score,
            workspace_name=ref.name,
            indexer_used=auth.indexer_used,
            rrf_k=int(hybrid_cfg["rrf_k"]),
            fts_config=str(hybrid_cfg["fts_config"]),
            debug=False,
        )
    else:
        hits = await vector_search(
            ws_pool,
            query_vec=query_vec,
            top_k=pre_top_k,
            min_score=min_score,
            workspace_name=ref.name,
            indexer_used=auth.indexer_used,
        )

    # Rerank conditionnel : config présente + > 1 hit (singleton skip)
    if rerank_cfg and len(hits) > 1:
        rerank_api_key: str | None = None
        if rerank_cfg["api_key_ref"]:
            rerank_api_key = await secret_resolver.resolve_with_retry(
                _to_vault_ref(rerank_cfg["api_key_ref"], default_vault_name)
            )
        reranker = rerank_factory(
            provider=rerank_cfg["provider"],
            model=rerank_cfg["model"],
            api_key=rerank_api_key,
            base_url=rerank_cfg["base_url"],
        )
        documents = [h.content for h in hits]
        indices = await reranker.rerank(query=query, documents=documents, top_k=top_k)
        hits = [hits[i] for i in indices]
        log.info(
            "mcp.rerank.applied",
            workspace=ref.name,
            pre_hits=len(documents),
            post_hits=len(hits),
            provider=rerank_cfg["provider"],
            model=rerank_cfg["model"],
        )
    elif rerank_cfg:
        log.debug(
            "mcp.rerank.skipped_singleton_or_empty",
            workspace=ref.name,
            hits=len(hits),
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
        hits=hits[:top_k],
    )
