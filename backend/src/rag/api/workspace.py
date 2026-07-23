from __future__ import annotations

import uuid as _uuid_mod
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from rag.auth.workspace_auth import AuthContext, require_workspace_apikey
from rag.schemas.workspace import (
    DeleteAsyncResponse,
    PushAsyncResponse,
    PushRequest,
    ReindexAsyncResponse,
    ReindexRequest,
)
from rag.services.chunking_routing import UnknownStrategySlugError, resolve_caller_strategy
from rag.services.push import normalize_path


async def _resolve_strategy_id(
    pool: asyncpg.Pool, owner_id: str, slug: str | None
) -> UUID | None:
    """Résout un slug de stratégie dans la bibliothèque du caller (mode service,
    spec chunking §5). Introuvable → 422 explicite, pas de repli sur l'extension."""
    if not slug:
        return None
    try:
        record = await resolve_caller_strategy(pool, owner_id=owner_id, slug=slug)
    except UnknownStrategySlugError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return record.id


async def _enqueue_push(
    pool: asyncpg.Pool,
    *,
    workspace_id: UUID,
    triggered_by: str,
    path: str,
    content: str,
    title: str | None,
    strategy_id: UUID | None,
    force: bool,
    correlation_id: str,
    source_url: str | None = None,
) -> str:
    """Enfile un job d'indexation + son payload. `force` bypasse le dedup."""
    async with pool.acquire() as conn, conn.transaction():
        job_id = await conn.fetchval(
            """
            INSERT INTO index_jobs (workspace_id, triggered_by, status, correlation_id)
            VALUES ($1, $2, 'pending', $3)
            RETURNING id
            """,
            workspace_id,
            triggered_by,
            correlation_id,
        )
        await conn.execute(
            "INSERT INTO push_job_payloads "
            "(job_id, path, content, title, strategy_id, force, source_url) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
            job_id,
            path,
            content,
            title,
            strategy_id,
            force,
            source_url,
        )
    return str(job_id)


def build_workspace_router() -> APIRouter:
    router = APIRouter(tags=["workspace"])

    @router.post(
        "/workspaces/{name}/index",
        status_code=202,
        tags=["apikey"],
        summary="Indexer un document",
        description="Pousse un document dans le workspace pour indexation "
        "(chunking + embeddings). Idempotent : contenu inchangé → job 'skipped'.",
    )
    async def push_index(
        name: str,
        payload: PushRequest,
        request: Request,
        auth: AuthContext = Depends(require_workspace_apikey),  # noqa: B008
    ) -> Response:
        norm_path = normalize_path(payload.path)
        correlation_id = str(_uuid_mod.uuid4())
        pool: asyncpg.Pool = request.app.state.pools.config_pool

        strategy_id = await _resolve_strategy_id(pool, auth.owner_id, payload.strategy)
        job_id = await _enqueue_push(
            pool,
            workspace_id=auth.workspace_id,
            triggered_by="push",
            path=norm_path,
            content=payload.content,
            title=payload.title,
            strategy_id=strategy_id,
            force=False,
            correlation_id=correlation_id,
            source_url=payload.source_url,
        )

        body = PushAsyncResponse(job_id=job_id, status="pending")
        return JSONResponse(
            content=body.model_dump(),
            status_code=202,
            headers={"X-Correlation-ID": correlation_id},
        )

    @router.post(
        "/workspaces/{name}/reindex/{path:path}",
        status_code=202,
        tags=["apikey"],
        summary="Ré-évaluer un document",
        description="Force la ré-indexation d'un document déjà poussé (le contenu "
        "est renvoyé dans le corps) même si le contenu est identique — pour "
        "appliquer une stratégie de chunking ou un modèle d'embedding modifié.",
    )
    async def reindex_document(
        name: str,
        path: str,
        payload: ReindexRequest,
        request: Request,
        auth: AuthContext = Depends(require_workspace_apikey),  # noqa: B008
    ) -> Response:
        norm_path = normalize_path(path)
        correlation_id = str(_uuid_mod.uuid4())
        pool: asyncpg.Pool = request.app.state.pools.config_pool

        strategy_id = await _resolve_strategy_id(pool, auth.owner_id, payload.strategy)
        job_id = await _enqueue_push(
            pool,
            workspace_id=auth.workspace_id,
            triggered_by="reindex_document",
            path=norm_path,
            content=payload.content,
            title=payload.title,
            strategy_id=strategy_id,
            force=True,
            correlation_id=correlation_id,
            source_url=payload.source_url,
        )

        body = ReindexAsyncResponse(job_id=job_id, status="pending")
        return JSONResponse(
            content=body.model_dump(),
            status_code=202,
            headers={"X-Correlation-ID": correlation_id},
        )

    @router.delete(
        "/workspaces/{name}/index/{path:path}",
        status_code=202,
        tags=["apikey"],
        summary="Supprimer un document",
        description="Supprime un document du workspace (chunks + embeddings + "
        "marqueur d'indexation) à partir de son path.",
    )
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
