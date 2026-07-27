from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from rag.schemas.mcp import McpRequest, McpResponse
from rag.services.mcp import normalize_refs, search


def build_mcp_router() -> APIRouter:
    """Router de l'API REST de recherche (`POST /api/v1/search`).

    À NE PAS confondre avec le serveur MCP protocolaire monté sur `/mcp` : ceci
    est une API JSON maison (recherche multi-workspaces en un appel, auth par
    api_key dans le body — cf. spec 04-api-mcp.md). Elle a migré de `/mcp` vers
    `/api/v1/search` pour libérer `/mcp` au profit du connecteur MCP.
    `services.mcp._authenticate` valide chaque workspace listé.
    """
    router = APIRouter(tags=["search"])

    @router.post("/api/v1/search", response_model=McpResponse, tags=["apikey"])
    async def post_search(payload: McpRequest, request: Request) -> McpResponse:
        refs = normalize_refs(payload)
        provider = request.app.state.client_provider
        default_vault = await provider.get_default_vault_name()
        if default_vault is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "no_default_vault_configured"},
            )
        hits, channels = await search(
            refs=refs,
            query=payload.query,
            top_k=payload.top_k,
            min_score=payload.min_score,
            config_pool=request.app.state.pools.config_pool,
            pool_registry=request.app.state.pools,
            secret_resolver=request.app.state.resolver,
            default_vault_name=default_vault,
        )
        return McpResponse(
            query=payload.query,
            results=hits,
            channels=channels if payload.debug else None,
        )

    return router
