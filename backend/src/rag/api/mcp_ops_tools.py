from __future__ import annotations

from contextvars import ContextVar
from typing import Any

import structlog

from rag.api.mcp_library_support import dump
from rag.services.chunking_configs import ChunkingConfigNotFound, get_chunking_config
from rag.services.hybrid_configs import get_hybrid_config
from rag.services.jobs import JobNotFound, get_job, list_job_files, list_jobs
from rag.services.rerank_configs import get_rerank_config
from rag.services.workspaces import resolve_owned_workspace_id

log = structlog.get_logger(__name__)

_UNKNOWN_WS = (
    "Workspace '{ws}' introuvable. Appelle list_workspaces() pour les slugs accessibles."
)


def register_ops_tools(mcp: Any, ws_ctx: ContextVar[Any]) -> None:
    """Outils MCP d'exploitation en LECTURE : jobs d'indexation + config de chunking.

    Owner-scopés comme les autres outils : le workspace ciblé doit être partagé
    ou possédé par le principal de la requête (résolu via resolve_owned_workspace_id).
    Réutilisent les MÊMES services que les endpoints REST (zéro duplication).
    """

    async def _owned_ws_id(ctx: Any, workspace: str) -> object | None:
        async with ctx.config_pool.acquire() as conn:
            return await resolve_owned_workspace_id(conn, name=workspace, owner_id=ctx.owner_id)

    @mcp.tool()
    async def list_index_jobs(workspace: str, limit: int = 20) -> str:
        """Historique des jobs d'indexation d'un workspace (plus récents en premier).

        Un job = une opération d'indexation (push, ré-évaluation, suppression, sync git…).
        Utile pour suivre l'état d'un push/reindex lancé de façon asynchrone.

        - workspace : slug du workspace (voir list_workspaces)
        - limit     : nombre maximum de jobs à retourner (défaut 20)

        Sortie : JSON [{id, triggered_by, status, files_changed, files_skipped,
        error_message, started_at, finished_at, duration_ms}]. Lecture seule.
        """
        ctx = ws_ctx.get()
        if await _owned_ws_id(ctx, workspace) is None:
            return _UNKNOWN_WS.format(ws=workspace)
        jobs = await list_jobs(ctx.config_pool, workspace_name=workspace)
        return dump(jobs[:limit])

    @mcp.tool()
    async def get_index_job(workspace: str, job_id: str) -> str:
        """Statut détaillé d'un job d'indexation + la liste des fichiers traités.

        - workspace : slug du workspace (voir list_workspaces)
        - job_id    : identifiant du job (retourné par push/reindex ou list_index_jobs)

        Sortie : JSON {job: {...statut...}, files: [{path, change_type}], files_total}.
        Message d'erreur si le job n'existe pas ou n'appartient pas au workspace.
        Lecture seule.
        """
        ctx = ws_ctx.get()
        if await _owned_ws_id(ctx, workspace) is None:
            return _UNKNOWN_WS.format(ws=workspace)
        try:
            job = await get_job(ctx.config_pool, workspace_name=workspace, job_id=job_id)
            files = await list_job_files(
                ctx.config_pool, workspace_name=workspace, job_id=job_id
            )
        except JobNotFound:
            return f"Job '{job_id}' introuvable dans le workspace '{workspace}'."
        return dump({"job": job, "files": files["files"], "files_total": files["total"]})

    @mcp.tool()
    async def get_chunking_configuration(workspace: str) -> str:
        """Configuration de chunking effective d'un workspace (algo + paramètres).

        - workspace : slug du workspace (voir list_workspaces)

        Sortie : JSON {strategy, max_chars, min_chars, overlap_chars, extras,
        default_strategy_id, engine, created_at, updated_at}. Décrit comment les
        documents sont découpés avant embedding. Lecture seule.
        """
        ctx = ws_ctx.get()
        ws_id = await _owned_ws_id(ctx, workspace)
        if ws_id is None:
            return _UNKNOWN_WS.format(ws=workspace)
        try:
            cfg = await get_chunking_config(ws_id, ctx.config_pool)
        except ChunkingConfigNotFound:
            return f"Aucune configuration de chunking pour le workspace '{workspace}'."
        return dump(cfg)

    @mcp.tool()
    async def get_rerank_configuration(workspace: str) -> str:
        """Configuration de reranking d'un workspace (provider, modèle, top_k).

        - workspace : slug du workspace (voir list_workspaces)

        Sortie : JSON {provider, model, base_url, top_k_pre_rerank} ou un message
        si le reranking n'est pas configuré (recherche sans reranker). La réf de
        clé API n'est pas exposée. Lecture seule.
        """
        ctx = ws_ctx.get()
        ws_id = await _owned_ws_id(ctx, workspace)
        if ws_id is None:
            return _UNKNOWN_WS.format(ws=workspace)
        cfg = await get_rerank_config(ws_id, ctx.config_pool)
        if cfg is None:
            return f"Aucun reranking configuré pour le workspace '{workspace}'."
        return dump(
            {
                "provider": cfg["provider"],
                "model": cfg["model"],
                "base_url": cfg["base_url"],
                "top_k_pre_rerank": cfg["top_k_pre_rerank"],
            }
        )

    @mcp.tool()
    async def get_hybrid_configuration(workspace: str) -> str:
        """Configuration de recherche hybride d'un workspace (fusion lexical/vectoriel).

        - workspace : slug du workspace (voir list_workspaces)

        Sortie : JSON {enabled, rrf_k, weight_lexical, weight_vector, lexical_engine}
        ou un message si la recherche est en vectoriel pur. Lecture seule.
        """
        ctx = ws_ctx.get()
        ws_id = await _owned_ws_id(ctx, workspace)
        if ws_id is None:
            return _UNKNOWN_WS.format(ws=workspace)
        cfg = await get_hybrid_config(ws_id, ctx.config_pool)
        if cfg is None:
            return f"Recherche vectorielle pure (pas d'hybride) pour '{workspace}'."
        return dump(
            {
                "enabled": cfg["enabled"],
                "rrf_k": cfg["rrf_k"],
                "weight_lexical": float(cfg["weight_lexical"]),
                "weight_vector": float(cfg["weight_vector"]),
                "lexical_engine": cfg["lexical_engine"],
            }
        )
