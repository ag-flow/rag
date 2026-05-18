from __future__ import annotations

import asyncpg
import structlog

from rag.db.workspace_migrations.runner import apply_pending

log = structlog.get_logger(__name__)


async def apply_pending_for_all_workspaces(config_pool: asyncpg.Pool) -> None:
    """Itère sur tous les workspaces et applique leurs migrations workspace manquantes.

    Fail-fast : si une base est inaccessible ou une migration plante, raise. Le
    service refuse alors de démarrer.
    """
    rows = await config_pool.fetch("SELECT name, rag_cnx FROM workspaces ORDER BY name")
    for row in rows:
        name = row["name"]
        dsn = row["rag_cnx"]
        try:
            applied = await apply_pending(dsn)
            if applied:
                log.info(
                    "workspace_migrations.boot_applied",
                    workspace=name,
                    count=applied,
                )
        except Exception:
            log.error(
                "workspace_migrations.boot_failed",
                workspace=name,
                exc_info=True,
            )
            raise
