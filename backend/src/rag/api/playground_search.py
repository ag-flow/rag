from __future__ import annotations

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from rag.api.workspace_access import require_owned_workspace_id
from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.schemas.mcp import ChannelHit
from rag.schemas.playground import (
    ChunkResult,
    PlaygroundSearchRequest,
    PlaygroundSearchResponse,
)

log = structlog.get_logger(__name__)

router_search = APIRouter(
    prefix="/api/workspaces",
    tags=["playground-search"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)

_WS_QUERY = """
    SELECT w.id AS ws_id, w.rag_cnx,
           ic.provider AS idx_provider, ic.model AS idx_model,
           ic.api_key_ref AS idx_api_key_ref, ic.base_url AS idx_base_url,
           md.service AS idx_service
    FROM workspaces w
    JOIN indexer_configs ic ON ic.workspace_id = w.id
    JOIN model_dimensions md ON md.provider = ic.provider AND md.model = ic.model
    WHERE w.name = $1
"""


def _to_channel(entries: list[object]) -> list[ChannelHit]:
    return [
        ChannelHit(path=e.path, chunk_index=e.chunk_index, rank=e.rank, score=e.score)  # type: ignore[attr-defined]
        for e in entries
    ]


async def perform_workspace_search(
    request: Request,
    workspace_name: str,
    *,
    query: str,
    top_k: int,
    min_score: float,
) -> PlaygroundSearchResponse:
    """Recherche du produit côté serveur (session), config hybride du
    workspace respectée. Réutilisée par le Playground ET le banc de test
    (feature 1a9b8b67) — le caller a déjà validé l'accès au workspace."""
    from rag.api.playground import make_harpo_resolver
    from rag.db.lexical_engines import get_lexical_engine
    from rag.db.workspace_search import hybrid_search, vector_search
    from rag.indexer.providers.factory import make_provider
    from rag.services.mcp import _load_hybrid_config

    config_pool: asyncpg.Pool = request.app.state.pools.config_pool
    pool_registry = request.app.state.pools
    resolve_harpo = make_harpo_resolver(request)

    ws_row = await config_pool.fetchrow(_WS_QUERY, workspace_name)
    if ws_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "workspace not found")

    indexer_api_key: str | None = None
    if ws_row["idx_api_key_ref"]:
        indexer_api_key = await resolve_harpo(ws_row["idx_api_key_ref"])
    provider = make_provider(
        service=ws_row["idx_service"],
        provider=ws_row["idx_provider"],
        model=ws_row["idx_model"],
        api_key=indexer_api_key,
        base_url=ws_row["idx_base_url"],
    )
    query_vec = await provider.embed_query(query)

    ws_pool = await pool_registry.get_workspace_pool(workspace_name, ws_row["rag_cnx"])
    indexer_used = f"{ws_row['idx_provider']}/{ws_row['idx_model']}"
    cfg = await _load_hybrid_config(config_pool, ws_row["ws_id"])
    hybrid_enabled = cfg is not None and bool(cfg["enabled"])

    if hybrid_enabled and cfg is not None:
        result = await hybrid_search(
            ws_pool,
            query_vec=query_vec,
            query=query,
            top_k=top_k,
            min_score=min_score,
            workspace_name=workspace_name,
            indexer_used=indexer_used,
            lexical_engine=get_lexical_engine(cfg["lexical_engine"]),
            rrf_k=cfg["rrf_k"],
            w_vector=cfg["weight_vector"],
            w_lexical=cfg["weight_lexical"],
        )
        hits = result.hits
        vector_channel = _to_channel(result.vector_channel)
        lexical_channel = _to_channel(result.lexical_channel)
    else:
        hits = await vector_search(
            ws_pool,
            query_vec=query_vec,
            top_k=top_k,
            min_score=min_score,
            workspace_name=workspace_name,
            indexer_used=indexer_used,
        )
        vector_channel = [
            ChannelHit(path=h.path, chunk_index=h.chunk_index, rank=i + 1, score=h.score)
            for i, h in enumerate(hits)
        ]
        lexical_channel = []

    log.info(
        "playground.search",
        workspace=workspace_name,
        hybrid=hybrid_enabled,
        hits=len(hits),
    )
    return PlaygroundSearchResponse(
        query=query,
        hybrid_enabled=hybrid_enabled,
        rrf_k=cfg["rrf_k"] if cfg is not None else 60,
        weight_vector=float(cfg["weight_vector"]) if cfg is not None else 0.5,
        weight_lexical=float(cfg["weight_lexical"]) if cfg is not None else 0.5,
        lexical_engine=cfg["lexical_engine"] if cfg is not None else "fts",
        hits=[
            ChunkResult(path=h.path, chunk_index=h.chunk_index, content=h.content, score=h.score)
            for h in hits
        ],
        vector_channel=vector_channel,
        lexical_channel=lexical_channel,
    )


@router_search.post(
    "/{workspace_name}/playground/search", response_model=PlaygroundSearchResponse
)
async def playground_search(
    workspace_name: str,
    body: PlaygroundSearchRequest,
    request: Request,
) -> PlaygroundSearchResponse:
    """Recherche seule (sans LLM), provenance par canal toujours renvoyée (D8, SR5.2)."""
    config_pool: asyncpg.Pool = request.app.state.pools.config_pool
    await require_owned_workspace_id(request, workspace_name, config_pool)
    return await perform_workspace_search(
        request,
        workspace_name,
        query=body.query,
        top_k=body.top_k,
        min_score=body.min_score,
    )
