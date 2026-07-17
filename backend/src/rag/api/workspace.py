from __future__ import annotations

import uuid as _uuid_mod
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from rag.auth.workspace_auth import AuthContext, require_workspace_apikey
from rag.schemas.workspace import DeleteAsyncResponse, PushAsyncResponse, PushRequest
from rag.services.chunking_routing import UnknownStrategySlugError, resolve_caller_strategy
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

        # Mode service (spec chunking §5) : le slug est résolu ICI, dans la
        # bibliothèque du caller puis côté système — le job ne reçoit que
        # l'id lié. Introuvable → 422 explicite, pas de repli sur l'extension.
        strategy_id: UUID | None = None
        if payload.strategy:
            try:
                record = await resolve_caller_strategy(
                    pool, owner_id=auth.owner_id, slug=payload.strategy
                )
            except UnknownStrategySlugError as exc:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
            strategy_id = record.id

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
                "INSERT INTO push_job_payloads (job_id, path, content, title, strategy_id) "
                "VALUES ($1, $2, $3, $4, $5)",
                job_id,
                norm_path,
                payload.content,
                payload.title,
                strategy_id,
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
