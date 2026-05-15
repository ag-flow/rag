from __future__ import annotations

from fastapi import APIRouter, Request

from rag.schemas.mcp import McpRequest, McpResponse
from rag.services.mcp import normalize_refs, search


def build_mcp_router() -> APIRouter:
    """Router de l'endpoint MCP search.

    Pas d'auth FastAPI dependency : la validation api_key est dans le body
    (cf. spec officielle 04-api-mcp.md). `services.mcp._authenticate` valide
    chaque workspace listé.
    """
    router = APIRouter(tags=["mcp"])

    @router.post("/mcp", response_model=McpResponse)
    async def post_mcp(payload: McpRequest, request: Request) -> McpResponse:
        refs = normalize_refs(payload)
        hits = await search(
            refs=refs,
            query=payload.query,
            top_k=payload.top_k,
            min_score=payload.min_score,
            config_pool=request.app.state.pools.config_pool,
            pool_registry=request.app.state.pools,
            apikey_cache=request.app.state.apikey_cache,
            secret_resolver=request.app.state.resolver,
        )
        return McpResponse(query=payload.query, results=hits)

    return router
