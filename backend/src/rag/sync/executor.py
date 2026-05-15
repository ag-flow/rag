from __future__ import annotations

import json

import asyncpg
import structlog

from rag.schemas.sync import JobToProcess

log = structlog.get_logger(__name__)


async def pick_next_pending_job(
    config_pool: asyncpg.Pool,
) -> JobToProcess | None:
    """Picke le job pending le plus ancien et le transitionne en running
    atomiquement (CTE + UPDATE … FROM).

    Retourne `None` si aucun job pending. Sinon retourne un `JobToProcess`
    avec tout le contexte nécessaire à l'executor (workspace, source, indexer).

    `FOR UPDATE SKIP LOCKED` rend l'opération safe pour multi-worker M3+.
    """
    async with config_pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """
            WITH picked AS (
                SELECT id FROM index_jobs
                WHERE status = 'pending'
                ORDER BY id
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            UPDATE index_jobs j
            SET status='running', started_at=now()
            FROM picked
            WHERE j.id = picked.id
            RETURNING
                j.id AS job_id,
                j.workspace_id,
                j.source_id
            """
        )
        if row is None:
            return None

        context = await conn.fetchrow(
            """
            SELECT
                w.name AS workspace_name,
                ws.config AS source_config,
                ic.provider AS indexer_provider,
                ic.model AS indexer_model
            FROM workspaces w
            LEFT JOIN workspace_sources ws ON ws.id = $1
            LEFT JOIN indexer_configs ic ON ic.workspace_id = w.id
            WHERE w.id = $2
            """,
            row["source_id"],
            row["workspace_id"],
        )

    if context is None:
        log.error("sync.picker.workspace_not_found", workspace_id=str(row["workspace_id"]))
        return None

    # asyncpg renvoie le jsonb sous forme de str dans ce repo
    raw_cfg = context["source_config"]
    source_config = json.loads(raw_cfg) if isinstance(raw_cfg, str) else dict(raw_cfg or {})

    return JobToProcess(
        job_id=row["job_id"],
        workspace_id=row["workspace_id"],
        workspace_name=context["workspace_name"],
        source_id=row["source_id"],
        source_config=source_config,
        indexer_provider=context["indexer_provider"] or "",
        indexer_model=context["indexer_model"] or "",
    )
