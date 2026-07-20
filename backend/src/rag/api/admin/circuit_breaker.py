from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from rag.api.workspace_access import require_owned_workspace_id
from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.services.circuit_breaker import close_circuit, get_circuit


def build_circuit_breaker_router() -> APIRouter:
    router = APIRouter(tags=["circuit-breaker"])

    @router.get("/workspaces/{name}/circuit-breaker")
    async def get_circuit_breaker(
        name: str,
        request: Request,
        _auth: None = Depends(require_master_key_or_authenticated_admin),      ) -> Response:
        pool = request.app.state.pools.config_pool
        workspace_id = await require_owned_workspace_id(request, name, pool)

        circuit = await get_circuit(pool, workspace_id=workspace_id)
        if circuit is None:
            return JSONResponse({"status": "closed"})

        return JSONResponse({
            "status": "open",
            "provider": circuit["provider"],
            "model": circuit["model"],
            "opened_at": circuit["opened_at"].isoformat(),
            "open_until": circuit["open_until"].isoformat() if circuit["open_until"] else None,
            "error_message": circuit["error_message"],
        })

    @router.post("/workspaces/{name}/circuit-breaker/close", status_code=204)
    async def close_circuit_breaker(
        name: str,
        request: Request,
        _auth: None = Depends(require_master_key_or_authenticated_admin),      ) -> Response:
        pool = request.app.state.pools.config_pool
        workspace_id = await require_owned_workspace_id(request, name, pool)

        closed = await close_circuit(pool, workspace_id=workspace_id)
        if not closed:
            raise HTTPException(status_code=404, detail="no_open_circuit")
        return Response(status_code=204)

    return router
