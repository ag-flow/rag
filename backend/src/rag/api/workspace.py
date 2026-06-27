from __future__ import annotations

import uuid as _uuid_mod

import asyncpg
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from rag.auth.workspace_auth import AuthContext, require_workspace_apikey
from rag.schemas.workspace import DeleteAsyncResponse, PushAsyncResponse, PushRequest
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

        async with pool.acquire() as conn, conn.transaction():
            job_id = await conn.fetchval(
                """
                INSERT INTO index_jobs (workspace_id, triggered_by, status, correlation_id)
                VALUES ($1, 'push', 'pending', $2)
                RETURNING id
                """,
                auth.workspace_id,
                correlation_id,
            )
            await conn.execute(
                "INSERT INTO push_job_payloads (job_id, path, content, title, strategy_override) "
                "VALUES ($1, $2, $3, $4, $5)",
                job_id,
                norm_path,
                payload.content,
                payload.title,
                payload.strategy,
            )

        body = PushAsyncResponse(job_id=str(job_id), status="pending")
        return JSONResponse(
            content=body.model_dump(),
            status_code=202,
            headers={"X-Correlation-ID": correlation_id},
        )

    @router.delete("/workspaces/{name}/index/{path:path}", status_code=202)
    async def delete_index(
        name: str,
        path: str,
        request: Request,
        auth: AuthContext = Depends(require_workspace_apikey),  # noqa: B008
    ) -> Response:
        norm_path = normalize_path(path)
        correlation_id = str(_uuid_mod.uuid4())
        pool: asyncpg.Pool = request.app.state.pools.config_pool

        async with pool.acquire() as conn, conn.transaction():
            job_id = await conn.fetchval(
                """
                INSERT INTO index_jobs (workspace_id, triggered_by, status, correlation_id)
                VALUES ($1, 'delete', 'pending', $2)
                RETURNING id
                """,
                auth.workspace_id,
                correlation_id,
            )
            await conn.execute(
                "INSERT INTO delete_job_payloads (job_id, path) VALUES ($1, $2)",
                job_id,
                norm_path,
            )

        body = DeleteAsyncResponse(job_id=str(job_id), status="pending")
        return JSONResponse(
            content=body.model_dump(),
            status_code=202,
            headers={"X-Correlation-ID": correlation_id},
        )

    return router
