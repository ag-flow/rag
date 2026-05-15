from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from rag.auth.workspace_auth import AuthContext, require_workspace_apikey
from rag.schemas.workspace import PushRequest, PushResponse
from rag.services.push import push_document


def build_workspace_router() -> APIRouter:
    """Router des endpoints workspace authentifiés par api_key.

    Pour le moment : un seul endpoint, `POST /workspaces/{name}/index` (M4b).
    L'auth est appliquée endpoint par endpoint (pas globalement) : M4c
    (recherche MCP) utilisera un schéma d'auth différent.
    """
    router = APIRouter(tags=["workspace"])

    @router.post("/workspaces/{name}/index", response_model=PushResponse)
    async def push_index(
        name: str,
        payload: PushRequest,
        request: Request,
        auth: AuthContext = Depends(require_workspace_apikey),  # noqa: B008
    ) -> PushResponse:
        return await push_document(
            payload=payload,
            workspace_id=auth.workspace_id,
            indexer_used=auth.indexer_used,
            config_pool=request.app.state.pools.config_pool,
            indexer=request.app.state.indexer,
        )

    return router
