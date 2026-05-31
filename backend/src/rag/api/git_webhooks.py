from __future__ import annotations

import json

import asyncpg
import structlog
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from rag.sync.webhook_parsers import extract_branch
from rag.sync.webhook_validators import validate

log = structlog.get_logger(__name__)


def build_git_webhooks_router() -> APIRouter:
    router = APIRouter(tags=["git-webhooks"])

    @router.post(
        "/api/webhooks/git/{workspace_name}/{source_name}",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def receive_git_push(
        workspace_name: str,
        source_name: str,
        request: Request,
    ) -> dict:
        pool: asyncpg.Pool = request.app.state.pools.config_pool
        resolver = request.app.state.resolver

        raw_body = await request.body()

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT ws.id AS source_id, ws.config, ws.webhook_enabled,
                       w.id AS workspace_id
                FROM workspace_sources ws
                JOIN workspaces w ON w.id = ws.workspace_id
                WHERE w.name = $1 AND ws.name = $2
                """,
                workspace_name,
                source_name,
            )

        if row is None or not row["webhook_enabled"]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source not found")

        raw = row["config"]
        config = json.loads(raw) if isinstance(raw, str) else dict(raw)

        secret_ref: str | None = config.get("webhook_secret_ref")
        if not secret_ref:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="webhook_secret_ref missing",
            )

        secret = await resolver.resolve_with_retry(secret_ref)

        headers_lower = {k.lower(): v for k, v in request.headers.items()}
        provider: str = config.get("git_provider", "github")

        if not validate(provider, secret, headers_lower, raw_body):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature"
            )

        payload = json.loads(raw_body)
        pushed_branch = extract_branch(provider, payload)
        expected_branch: str = config.get("webhook_branch_filter") or config.get("branch", "main")

        if pushed_branch != expected_branch:
            log.info(
                "git_webhook.branch_mismatch",
                workspace=workspace_name,
                source=source_name,
                pushed=pushed_branch,
                expected=expected_branch,
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "ignored", "reason": "branch_mismatch"},
            )

        async with pool.acquire() as conn:
            job_row = await conn.fetchrow(
                """
                INSERT INTO index_jobs (workspace_id, source_id, triggered_by, status)
                VALUES ($1, $2, 'webhook', 'pending')
                RETURNING id
                """,
                row["workspace_id"],
                row["source_id"],
            )

        job_id = str(job_row["id"])
        log.info(
            "git_webhook.job_created",
            workspace=workspace_name,
            source=source_name,
            job_id=job_id,
        )
        return {"status": "pending", "job_id": job_id}

    return router
