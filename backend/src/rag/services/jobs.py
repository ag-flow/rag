from __future__ import annotations

from typing import Any

import asyncpg
import structlog

from rag.api.errors import WorkspaceNotFound
from rag.db.helpers import fetch_all, fetch_one

log = structlog.get_logger(__name__)


async def create_pending_job(
    *, workspace_name: str, triggered_by: str, config_pool: asyncpg.Pool
) -> dict[str, Any]:
    """Insère un job en status 'pending' pour le workspace.

    `triggered_by` ∈ {'manual', 'webhook', 'push', 'schedule', 'reindex_indexer_change'}.
    La validité est vérifiée par la CHECK constraint en base (migration 003).
    """
    row = await fetch_one(
        config_pool,
        """
        INSERT INTO index_jobs (workspace_id, triggered_by, status)
        SELECT id, $2, 'pending' FROM workspaces WHERE name = $1
        RETURNING id, triggered_by, status, files_changed, files_skipped,
                  error_message, started_at, finished_at, duration_ms
        """,
        workspace_name,
        triggered_by,
    )
    if row is None:
        raise WorkspaceNotFound(workspace_name)

    log.info("job.created_pending", workspace=workspace_name, triggered_by=triggered_by)
    return _job_to_dict(row)


async def list_jobs(config_pool: asyncpg.Pool, *, workspace_name: str) -> list[dict[str, Any]]:
    """Historique des jobs pour un workspace, plus récents en premier (started_at DESC).

    Lève WorkspaceNotFound si le workspace n'existe pas.
    """
    ws = await fetch_one(config_pool, "SELECT id FROM workspaces WHERE name=$1", workspace_name)
    if ws is None:
        raise WorkspaceNotFound(workspace_name)

    rows = await fetch_all(
        config_pool,
        """
        SELECT id, triggered_by, status, files_changed, files_skipped,
               error_message, started_at, finished_at, duration_ms
        FROM index_jobs
        WHERE workspace_id = $1
        ORDER BY started_at DESC NULLS LAST, id DESC
        """,
        ws["id"],
    )
    return [_job_to_dict(r) for r in rows]


def _job_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "triggered_by": row["triggered_by"],
        "status": row["status"],
        "files_changed": int(row["files_changed"] or 0),
        "files_skipped": int(row["files_skipped"] or 0),
        "error_message": row["error_message"],
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
        "duration_ms": row["duration_ms"],
    }
