from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from rag.auth.workspace_auth import ReadAuthContext, require_workspace_apikey_read
from rag.db.enrichment_lookup import get_enrichment as get_enrichment_db
from rag.db.mcp_tools import (
    get_document_status,
    get_index_status,
    reconstruct_document,
    search_files_in_workspace,
)
from rag.schemas.workspace_query import (
    DocumentResponse,
    EnrichmentResponse,
    FileHit,
    FilesResponse,
)
from rag.services.push import normalize_path


def build_workspace_query_router() -> APIRouter:
    """Endpoints de LECTURE par clé API (scope read+), équivalents REST des
    outils MCP de consultation : document, recherche littérale, statut, enrichissement.

    Chaque endpoint réutilise le MÊME service que l'outil MCP correspondant —
    aucune logique dupliquée.
    """
    router = APIRouter(tags=["workspace"])

    def _pools(request: Request):
        return request.app.state.pools

    @router.get(
        "/workspaces/{name}/files",
        tags=["apikey"],
        response_model=FilesResponse,
        summary="Rechercher des fichiers (littéral)",
        description="Recherche par correspondance littérale dans le corpus indexé "
        "(modes exact / substring / regex). Équivalent REST de l'outil MCP search_files.",
    )
    async def files(
        name: str,
        request: Request,
        pattern: str = Query(..., min_length=1),
        mode: str = Query("exact", pattern="^(exact|substring|regex)$"),
        top_k: int = Query(20, ge=1, le=200),
        auth: ReadAuthContext = Depends(require_workspace_apikey_read),  # noqa: B008
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
        "/workspaces/{name}/index-status",
        tags=["apikey"],
        summary="État de l'index",
        description="État global de l'index du workspace, ou d'un document précis si "
        "`path` est fourni. Équivalent REST de l'outil MCP index_status.",
    )
    async def index_status(
        name: str,
        request: Request,
        path: str | None = Query(None),
        auth: ReadAuthContext = Depends(require_workspace_apikey_read),  # noqa: B008
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
        "/workspaces/{name}/documents/{path:path}",
        tags=["apikey"],
        response_model=DocumentResponse,
        summary="Lire un document",
        description="Contenu reconstruit d'un document depuis l'index (sans accès disque). "
        "Refusé si le workspace interdit la lecture complète. Équivalent REST de get_document.",
    )
    async def document(
        name: str,
        path: str,
        request: Request,
        auth: ReadAuthContext = Depends(require_workspace_apikey_read),  # noqa: B008
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
        return DocumentResponse(path=norm_path, **result)

    @router.get(
        "/workspaces/{name}/enrichments/{path:path}",
        tags=["apikey"],
        response_model=EnrichmentResponse,
        summary="Lire un enrichissement",
        description="Métadonnée LLM pré-calculée d'un document, pour une clé donnée. "
        "Équivalent REST de l'outil MCP get_enrichment.",
    )
    async def enrichment(
        name: str,
        path: str,
        request: Request,
        key: str = Query(..., min_length=1),
        auth: ReadAuthContext = Depends(require_workspace_apikey_read),  # noqa: B008
    ) -> EnrichmentResponse:
        config_pool: asyncpg.Pool = _pools(request).config_pool
        norm_path = normalize_path(path)
        data = await get_enrichment_db(
            config_pool, workspace_id=auth.workspace_id, path=norm_path, key=key
        )
        if data is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "enrichment_not_found")
        return EnrichmentResponse(path=norm_path, key=key, **data)

    return router
