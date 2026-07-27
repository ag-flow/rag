from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from rag.auth.workspace_auth import (
    OwnerAuthContext,
    ReadAuthContext,
    require_apikey_owner,
    resolve_apikey_read_workspace,
)
from rag.db.enrichment_lookup import get_enrichment as get_enrichment_db
from rag.db.mcp_tools import (
    get_document_status,
    get_index_status,
    reconstruct_document,
    search_files_in_workspace,
)
from rag.schemas.admin import ChunkingConfigResponse, JobFilesResponse, JobResponse
from rag.schemas.workspace_query import (
    DocumentResponse,
    EnrichmentResponse,
    FileHit,
    FilesResponse,
    HybridConfigView,
    RerankConfigView,
)
from rag.services.chunking_configs import ChunkingConfigNotFound, get_chunking_config
from rag.services.hybrid_configs import get_hybrid_config
from rag.services.jobs import JobNotFound, get_job, list_job_files, list_jobs
from rag.services.push import normalize_path
from rag.services.rerank_configs import get_rerank_config


def build_workspace_query_router() -> APIRouter:
    """Endpoints de LECTURE par clé API (scope read+), équivalents REST des
    outils MCP de consultation.

    Le workspace est un PARAMÈTRE d'appel (query `?workspace=`), plus dans l'URL —
    cohérent avec les écritures (workspace dans le corps) et les outils MCP.
    Chaque endpoint réutilise le MÊME service que l'outil MCP correspondant.
    """
    router = APIRouter(tags=["workspace"])

    def _pools(request: Request):
        return request.app.state.pools

    async def _read_ctx(
        request: Request,
        workspace: str = Query(..., min_length=1, description="Slug du workspace cible"),
        owner: OwnerAuthContext = Depends(require_apikey_owner),  # noqa: B008
    ) -> ReadAuthContext:
        """Résout le contexte de lecture : clé → owner+scope, puis workspace (query)."""
        return await resolve_apikey_read_workspace(
            request, owner_id=owner.owner_id, scope=owner.scope, workspace=workspace
        )

    @router.get(
        "/files",
        tags=["apikey"],
        response_model=FilesResponse,
        summary="Rechercher des fichiers (littéral)",
        description="Recherche par correspondance littérale dans le corpus indexé "
        "(modes exact / substring / regex). Équivalent REST de l'outil MCP search_files.",
    )
    async def files(
        request: Request,
        pattern: str = Query(..., min_length=1),
        mode: str = Query("exact", pattern="^(exact|substring|regex)$"),
        top_k: int = Query(20, ge=1, le=200),
        auth: ReadAuthContext = Depends(_read_ctx),  # noqa: B008
    ) -> FilesResponse:
        ws_pool = await _pools(request).get_workspace_pool(auth.workspace_name, auth.rag_cnx)
        hits = await search_files_in_workspace(ws_pool, pattern=pattern, mode=mode, top_k=top_k)
        return FilesResponse(
            pattern=pattern,
            mode=mode,
            count=len(hits),
            hits=[FileHit(**h) for h in hits],
        )

    @router.get(
        "/index-status",
        tags=["apikey"],
        summary="État de l'index",
        description="État global de l'index du workspace, ou d'un document précis si "
        "`path` est fourni. Équivalent REST de l'outil MCP index_status.",
    )
    async def index_status(
        request: Request,
        path: str | None = Query(None),
        auth: ReadAuthContext = Depends(_read_ctx),  # noqa: B008
    ) -> dict[str, Any]:
        config_pool: asyncpg.Pool = _pools(request).config_pool
        if path:
            data = await get_document_status(
                config_pool, workspace_id=auth.workspace_id, path=normalize_path(path)
            )
            if data is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "document_not_indexed")
            return data
        data = await get_index_status(config_pool, workspace_id=auth.workspace_id)
        return {"workspace": auth.workspace_name, **data}

    @router.get(
        "/documents",
        tags=["apikey"],
        response_model=DocumentResponse,
        summary="Lire un document",
        description="Contenu reconstruit d'un document depuis l'index (sans accès disque). "
        "Refusé si le workspace interdit la lecture complète. Équivalent REST de get_document.",
    )
    async def document(
        request: Request,
        path: str = Query(..., min_length=1),
        auth: ReadAuthContext = Depends(_read_ctx),  # noqa: B008
    ) -> DocumentResponse:
        config_pool: asyncpg.Pool = _pools(request).config_pool
        allow = await config_pool.fetchval(
            "SELECT allow_full_read FROM workspaces WHERE id = $1", auth.workspace_id
        )
        if allow is False:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "full_read_not_allowed")

        norm_path = normalize_path(path)
        ws_pool = await _pools(request).get_workspace_pool(auth.workspace_name, auth.rag_cnx)
        result = await reconstruct_document(
            ws_pool, config_pool, workspace_id=auth.workspace_id, path=norm_path
        )
        if result is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "document_not_indexed")
        source_url = await config_pool.fetchval(
            "SELECT source_url FROM indexed_documents WHERE workspace_id=$1 AND path=$2",
            auth.workspace_id,
            norm_path,
        )
        return DocumentResponse(path=norm_path, source_url=source_url, **result)

    @router.get(
        "/enrichments",
        tags=["apikey"],
        response_model=EnrichmentResponse,
        summary="Lire un enrichissement",
        description="Métadonnée LLM pré-calculée d'un document, pour une clé donnée. "
        "Équivalent REST de l'outil MCP get_enrichment.",
    )
    async def enrichment(
        request: Request,
        path: str = Query(..., min_length=1),
        key: str = Query(..., min_length=1),
        auth: ReadAuthContext = Depends(_read_ctx),  # noqa: B008
    ) -> EnrichmentResponse:
        config_pool: asyncpg.Pool = _pools(request).config_pool
        norm_path = normalize_path(path)
        data = await get_enrichment_db(
            config_pool, workspace_id=auth.workspace_id, path=norm_path, key=key
        )
        if data is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "enrichment_not_found")
        return EnrichmentResponse(path=norm_path, key=key, **data)

    # ── Jobs d'indexation (équivalent apikey des endpoints admin) ────────────

    @router.get(
        "/jobs",
        tags=["apikey"],
        response_model=list[JobResponse],
        summary="Lister les jobs d'indexation",
        description="Historique des jobs du workspace (push, ré-évaluation, suppression, "
        "sync), plus récents en premier.",
    )
    async def jobs(
        request: Request,
        auth: ReadAuthContext = Depends(_read_ctx),  # noqa: B008
    ) -> list[JobResponse]:
        rows = await list_jobs(_pools(request).config_pool, workspace_name=auth.workspace_name)
        return [JobResponse(**r) for r in rows]

    @router.get(
        "/jobs/{job_id}",
        tags=["apikey"],
        response_model=JobResponse,
        summary="Statut d'un job",
        description="État détaillé d'un job d'indexation par son id (statut, compteurs, "
        "erreur, durée). Indispensable pour suivre un push/reindex renvoyé en 202.",
    )
    async def job_status(
        job_id: str,
        request: Request,
        auth: ReadAuthContext = Depends(_read_ctx),  # noqa: B008
    ) -> JobResponse:
        try:
            row = await get_job(
                _pools(request).config_pool, workspace_name=auth.workspace_name, job_id=job_id
            )
        except JobNotFound as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "job_not_found") from exc
        return JobResponse(**row)

    @router.get(
        "/jobs/{job_id}/files",
        tags=["apikey"],
        response_model=JobFilesResponse,
        summary="Fichiers d'un job",
        description="Liste des fichiers traités par un job (added/modified/deleted).",
    )
    async def job_files(
        job_id: str,
        request: Request,
        auth: ReadAuthContext = Depends(_read_ctx),  # noqa: B008
    ) -> JobFilesResponse:
        try:
            data = await list_job_files(
                _pools(request).config_pool, workspace_name=auth.workspace_name, job_id=job_id
            )
        except JobNotFound as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "job_not_found") from exc
        return JobFilesResponse(**data)

    # ── Config de chunking (lecture) ─────────────────────────────────────────

    @router.get(
        "/chunking-config",
        tags=["apikey"],
        response_model=ChunkingConfigResponse,
        summary="Lire la config de chunking",
        description="Configuration de chunking effective du workspace (algo, tailles, "
        "engine, stratégie par défaut).",
    )
    async def chunking_config(
        request: Request,
        auth: ReadAuthContext = Depends(_read_ctx),  # noqa: B008
    ) -> ChunkingConfigResponse:
        try:
            cfg = await get_chunking_config(auth.workspace_id, _pools(request).config_pool)
        except ChunkingConfigNotFound as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "chunking_config_not_found") from exc
        return ChunkingConfigResponse(
            workspace_id=cfg["workspace_id"],
            strategy=cfg["strategy"],
            max_chars=cfg["max_chars"],
            min_chars=cfg["min_chars"],
            overlap_chars=cfg["overlap_chars"],
            extras=cfg["extras"],
            default_strategy_id=cfg["default_strategy_id"],
            engine=cfg["engine"],
            created_at=cfg["created_at"].isoformat(),
            updated_at=cfg["updated_at"].isoformat(),
        )

    # ── Config de recherche : rerank + hybride (lecture) ─────────────────────

    @router.get(
        "/rerank",
        tags=["apikey"],
        response_model=RerankConfigView,
        summary="Lire la config de reranking",
        description="Configuration de reranking du workspace (provider, modèle, "
        "top_k avant rerank). 404 si non configuré. La réf de clé n'est pas exposée.",
    )
    async def rerank_config(
        request: Request,
        auth: ReadAuthContext = Depends(_read_ctx),  # noqa: B008
    ) -> RerankConfigView:
        cfg = await get_rerank_config(auth.workspace_id, _pools(request).config_pool)
        if cfg is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "rerank_not_configured")
        return RerankConfigView(
            provider=cfg["provider"],
            model=cfg["model"],
            base_url=cfg["base_url"],
            top_k_pre_rerank=cfg["top_k_pre_rerank"],
        )

    @router.get(
        "/hybrid-config",
        tags=["apikey"],
        response_model=HybridConfigView,
        summary="Lire la config de recherche hybride",
        description="Configuration de recherche hybride (fusion lexical/vectoriel : "
        "RRF k, poids, moteur lexical). 404 si vectoriel pur.",
    )
    async def hybrid_config(
        request: Request,
        auth: ReadAuthContext = Depends(_read_ctx),  # noqa: B008
    ) -> HybridConfigView:
        cfg = await get_hybrid_config(auth.workspace_id, _pools(request).config_pool)
        if cfg is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "hybrid_not_configured")
        return HybridConfigView(
            enabled=cfg["enabled"],
            rrf_k=cfg["rrf_k"],
            weight_lexical=float(cfg["weight_lexical"]),
            weight_vector=float(cfg["weight_vector"]),
            lexical_engine=cfg["lexical_engine"],
        )

    return router
