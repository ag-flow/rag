from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
import structlog

log = structlog.get_logger(__name__)


async def get_index_status(
    config_pool: asyncpg.Pool,
    *,
    workspace_id: UUID,
) -> dict[str, Any]:
    """Agrégats indexed_documents + bloc sync (workspace_sources + dernier index_job)."""
    agg = await config_pool.fetchrow(
        "SELECT COUNT(*) AS documents_count, MAX(indexed_at) AS last_indexed_at "
        "FROM indexed_documents WHERE workspace_id = $1",
        workspace_id,
    )
    src = await config_pool.fetchrow(
        "SELECT last_indexed_at, next_sync_at FROM workspace_sources "
        "WHERE workspace_id = $1 LIMIT 1",
        workspace_id,
    )
    job = await config_pool.fetchrow(
        "SELECT status, finished_at FROM index_jobs "
        "WHERE workspace_id = $1 ORDER BY finished_at DESC NULLS LAST LIMIT 1",
        workspace_id,
    )
    healthy = bool(job is None or job["status"] != "error")
    return {
        "documents_count": agg["documents_count"] if agg else 0,
        "last_indexed_at": str(agg["last_indexed_at"]) if agg and agg["last_indexed_at"] else None,
        "sync": {
            "last_indexed_at": (
                str(src["last_indexed_at"]) if src and src["last_indexed_at"] else None
            ),
            "next_sync_at": str(src["next_sync_at"]) if src and src["next_sync_at"] else None,
            "last_job_status": job["status"] if job else None,
            "last_job_finished_at": str(job["finished_at"]) if job and job["finished_at"] else None,
            "healthy": healthy,
        },
    }


async def get_document_status(
    config_pool: asyncpg.Pool,
    *,
    workspace_id: UUID,
    path: str,
) -> dict[str, Any] | None:
    """Fraîcheur et hash d'un document indexé."""
    row = await config_pool.fetchrow(
        "SELECT path, content_hash, indexed_at, indexer_used, title "
        "FROM indexed_documents WHERE workspace_id = $1 AND path = $2",
        workspace_id,
        path,
    )
    if row is None:
        return None
    return {
        "path": row["path"],
        "content_hash": row["content_hash"],
        "indexed_at": str(row["indexed_at"]) if row["indexed_at"] else None,
        "indexer_used": row["indexer_used"],
        "title": row["title"],
    }
