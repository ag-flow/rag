from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol

import asyncpg
import structlog
from fastapi import HTTPException, status

from rag.api.errors import WorkspaceNotFound
from rag.db.pool import WorkspacePoolRegistry
from rag.db.workspace_search import hybrid_search, vector_search
from rag.indexer.providers.factory import make_provider
from rag.indexer.providers.protocol import EmbeddingProvider
from rag.rerank.protocol import (
    RerankProvider,
    RerankProviderError,
    RerankProviderUnreachable,
    RerankResult,
)
from rag.rerank.providers.factory import make_rerank_provider as _make_rerank_default
from rag.schemas.mcp import MultiWorkspaceRequest, SearchHit, SingleWorkspaceRequest
from rag.secrets.refs import build_ref, is_vault_ref

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


async def _authenticate(
    *,
    ref: McpWorkspaceRef,
    config_pool: asyncpg.Pool,
) -> _CacheEntry:
    """Valide la paire (workspace_name, api_key) contre les clés utilisateur.

    Lookup O(1) par fingerprint SHA-256 dans `user_api_keys` : la valeur de la
    clé n'est jamais stockée en base. La recherche exige un grant `can_read`
    sur le workspace demandé.

    Retourne un `_CacheEntry` (workspace_id, indexer_used, inserted_at).
    - WorkspaceNotFound si workspace inconnu.
    - HTTPException 401 si la clé est invalide ou sans grant can_read.
    """
    fingerprint = sha256(ref.api_key.encode("utf-8")).hexdigest()

    row = await config_pool.fetchrow(
        """
        SELECT w.id,
               ic.provider || '/' || ic.model AS indexer_used
        FROM workspaces w
        JOIN user_api_key_workspaces g ON g.workspace_id = w.id
        JOIN user_api_keys k ON k.id = g.api_key_id
        JOIN indexer_configs ic ON ic.workspace_id = w.id
        WHERE w.name = $1
          AND k.fingerprint = $2
          AND g.can_read
          AND k.revoked_at IS NULL
          AND (k.rotated_at IS NULL OR k.rotated_at > now() - interval '72 hours')
        """,
        ref.name,
        fingerprint,
    )
    if row is None:
        # Workspace inconnu OU clé/grant invalide : distinguer 404 de 401.
        exists = await config_pool.fetchval(
            "SELECT 1 FROM workspaces WHERE name = $1", ref.name
        )
        if exists is None:
            raise WorkspaceNotFound(ref.name)
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


def _as_vault_ref(ref: str, default_vault_name: str) -> str:
    """Normalise un `api_key_ref` en ref vault complète, sans double-wrapper.

    `api_key_ref` peut être soit une clé logique (à préfixer avec le vault par
    défaut), soit déjà une ref complète `${vault://<name>:<path>}` (harpo_path
    d'une provider_api_key, cf IndexerCreateSpec). Wrapper inconditionnellement
    une ref déjà complète produit `${vault://X:${vault://...}}`, que le
    resolver ne sait pas parser (UnknownAction). Reflète
    `RealIndexer._resolve_api_key` (indexer/real.py).
    """
    if is_vault_ref(ref):
        return ref
    return _to_vault_ref(ref, default_vault_name)


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
    secret_resolver: _ResolverProtocol,
    default_vault_name: str = "rag",
    provider_factory: Callable[..., EmbeddingProvider] | None = None,
    rerank_factory: Callable[..., RerankProvider] | None = None,
    scope: str = "both",
    enrichment_keys: list[str] | None = None,
) -> list[SearchHit]:
    """Orchestre la recherche MCP multi-workspace.

    Fail-fast : la première exception remontée par un workspace (auth, embedding,
    accès DB…) propage via `asyncio.gather` et annule les autres tasks. Aucun
    résultat partiel. Exception : un échec du provider rerank
    (`RerankProviderError`) ne fait PAS échouer la recherche — `_search_one`
    retombe sur l'ordre vector/RRF non reranké (BUG-002).

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
            secret_resolver=secret_resolver,
            default_vault_name=default_vault_name,
            provider_factory=factory,
            rerank_factory=rfactory,
            scope=scope,
            enrichment_keys=enrichment_keys,
        )
        for r in refs
    ]
    results = await asyncio.gather(*tasks)
    return [hit for ws_result in results for hit in ws_result.hits]


def _validate_rerank_results(
    results: list[RerankResult], *, n_documents: int
) -> list[RerankResult]:
    """Filtre les paires (index, score) hors bornes ou dupliquées d'un reranker.

    Le protocole `RerankProvider` promet des indices dans range(n_documents),
    mais rien ne garantit qu'un provider (bug upstream, self-hosted buggé,
    changement d'API) respecte ce contrat. Un indice hors bornes provoquerait
    un IndexError ; un doublon dupliquerait silencieusement un hit.
    """
    valid: list[RerankResult] = []
    seen: set[int] = set()
    dropped: list[int] = []
    for i, score in results:
        if 0 <= i < n_documents and i not in seen:
            valid.append((i, score))
            seen.add(i)
        else:
            dropped.append(i)
    if dropped:
        log.warning(
            "mcp.rerank.invalid_indices_dropped",
            dropped=dropped,
            n_documents=n_documents,
        )
    if results and not valid:
        raise RerankProviderUnreachable(
            "rerank provider returned no valid indices "
            f"(n_documents={n_documents}, results={results})"
        )
    return valid


async def _search_one(
    *,
    ref: McpWorkspaceRef,
    query: str,
    top_k: int,
    min_score: float,
    config_pool: asyncpg.Pool,
    pool_registry: WorkspacePoolRegistry,
    secret_resolver: _ResolverProtocol,
    default_vault_name: str,
    provider_factory: Callable[..., EmbeddingProvider],
    rerank_factory: Callable[..., RerankProvider],
    scope: str = "both",
    enrichment_keys: list[str] | None = None,
) -> _WorkspaceResult:
    auth = await _authenticate(
        ref=ref,
        config_pool=config_pool,
    )
    ctx = await _load_workspace_context(config_pool, ref.name)

    api_key: str | None = None
    if ctx["api_key_ref"]:
        api_key = await secret_resolver.resolve_with_retry(
            _as_vault_ref(ctx["api_key_ref"], default_vault_name)
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
            scope=scope,
            enrichment_keys=enrichment_keys,
        )
    else:
        hits = await vector_search(
            ws_pool,
            query_vec=query_vec,
            top_k=pre_top_k,
            min_score=min_score,
            workspace_name=ref.name,
            indexer_used=auth.indexer_used,
            scope=scope,
            enrichment_keys=enrichment_keys,
        )

    # Rerank conditionnel : config présente + > 1 hit (singleton skip)
    if rerank_cfg and len(hits) > 1:
        rerank_api_key: str | None = None
        if rerank_cfg["api_key_ref"]:
            rerank_api_key = await secret_resolver.resolve_with_retry(
                _as_vault_ref(rerank_cfg["api_key_ref"], default_vault_name)
            )
        reranker = rerank_factory(
            provider=rerank_cfg["provider"],
            model=rerank_cfg["model"],
            api_key=rerank_api_key,
            base_url=rerank_cfg["base_url"],
        )
        documents = [h.content for h in hits]
        try:
            results = await reranker.rerank(query=query, documents=documents, top_k=top_k)
            results = _validate_rerank_results(results, n_documents=len(documents))
        except RerankProviderError as exc:
            # Fallback dégradé (BUG-002) : un échec provider (429 / timeout /
            # auth / 5xx) ne doit pas propager en HTTP 500 ni — via asyncio.gather
            # — annuler les autres workspaces d'une recherche multi. On conserve
            # l'ordre vector/RRF (tronqué à top_k au retour) et on trace un
            # avertissement plutôt que d'échouer la recherche.
            log.warning(
                "mcp.rerank.failed_fallback_to_base_order",
                workspace=ref.name,
                provider=rerank_cfg["provider"],
                model=rerank_cfg["model"],
                error=type(exc).__name__,
                detail=str(exc),
            )
        else:
            # Écrase `score` par le relevance_score du reranker (BUG-012) : la
            # réponse est ordonnée par le reranker, donc `score` doit rester
            # monotone avec cet ordre — sinon un tri/filtre client par score
            # réintroduit l'ordre pré-rerank. Copie sans mutation en place.
            hits = [
                hits[i].model_copy(
                    update={
                        "score": rscore,
                        "debug": (
                            hits[i].debug.model_copy(update={"rerank_score": rscore})
                            if hits[i].debug is not None
                            else None
                        ),
                    }
                )
                for i, rscore in results
            ]
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
