from __future__ import annotations

import uuid as _uuid_mod

import asyncpg
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from rag.auth.workspace_auth import AuthContext, require_workspace_apikey
from rag.schemas.workspace import PushAsyncResponse, PushRequest
from rag.services.push import normalize_path


def build_workspace_router() -> APIRouter:
    router = APIRouter(tags=["workspace"])

    @router.post("/workspaces/{name}/index", status_code=202)
    async def push_index(
        name: str,
        payload: PushRequest,
        request: Request,
        auth: AuthContext = Depends(require_workspace_apikey),  # noqa: B008
    ) -> Response:
        norm_path = normalize_path(payload.path)
        correlation_id = str(_uuid_mod.uuid4())
        pool: asyncpg.Pool = request.app.state.pools.config_pool

        job_id = await pool.fetchval(
            """
            INSERT INTO index_jobs (workspace_id, triggered_by, status, correlation_id)
            VALUES ($1, 'push', 'pending', $2)
            RETURNING id
            """,
            auth.workspace_id,
            correlation_id,
        )
        await pool.execute(
            "INSERT INTO push_job_payloads (job_id, path, content) VALUES ($1, $2, $3)",
            job_id,
            norm_path,
            payload.content,
        )

        body = PushAsyncResponse(job_id=str(job_id), status="pending")
        return JSONResponse(
            content=body.model_dump(),
            status_code=202,
            headers={"X-Correlation-ID": correlation_id},
        )

    return router
