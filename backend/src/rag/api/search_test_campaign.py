from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from rag.api.playground_search import perform_search
from rag.services import search_test as svc

# Extrait stocké avec chaque hit retourné : assez pour comprendre pourquoi un
# passage remonte, sans dupliquer le corpus dans l'historique des runs.
SNIPPET_CHARS = 240
CAMPAIGN_TOP_K = 10


async def launch_campaign(
    *,
    config_pool: asyncpg.Pool,
    pool_registry: Any,
    resolve_harpo: Any,
    workspace_id: UUID,
    workspace_name: str,
) -> dict[str, Any]:
    """Lance une campagne du banc de test — cœur partagé IHM (REST) et MCP.

    Config hybride du workspace respectée et snapshotée dans le run ; chaque
    résultat persiste le top-k retourné (path, score, snippet, matched) pour
    l'analyse a posteriori (migration 093). Lève ValueError si aucune question
    activée.
    """
    from rag.services.mcp import _load_hybrid_config

    hybrid = await _load_hybrid_config(config_pool, workspace_id)
    config: dict[str, Any] = (
        {
            "hybrid": bool(hybrid["enabled"]),
            "lexical_engine": hybrid["lexical_engine"],
            "weight_vector": float(hybrid["weight_vector"]),
            "weight_lexical": float(hybrid["weight_lexical"]),
            "rrf_k": int(hybrid["rrf_k"]),
        }
        if hybrid is not None
        else {"hybrid": False}
    )

    async def search_fn(question: str) -> list[dict[str, Any]]:
        resp = await perform_search(
            config_pool=config_pool,
            pool_registry=pool_registry,
            resolve_harpo=resolve_harpo,
            workspace_name=workspace_name,
            query=question,
            top_k=CAMPAIGN_TOP_K,
            min_score=0.0,
        )
        return [
            {
                "path": h.path,
                "score": h.score,
                "chunk_index": h.chunk_index,
                "snippet": h.content[:SNIPPET_CHARS],
            }
            for h in resp.hits
        ]

    return await svc.run_campaign(
        config_pool,
        workspace_id=workspace_id,
        search_fn=search_fn,
        config=config,
        top_k=CAMPAIGN_TOP_K,
    )
