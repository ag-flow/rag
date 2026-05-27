from __future__ import annotations

import asyncpg
import structlog

log = structlog.get_logger(__name__)


async def reset_stale_running_jobs(config_pool: asyncpg.Pool) -> int:
    """Marque tous les jobs `running` en `error` au boot (crash recovery).

    Un job `running` au démarrage signifie que le worker a crashé entre
    `started_at` et `finished_at`. Le marquer `error` libère la source
    pour un retry naturel au prochain cycle.

    Retourne le nombre de jobs affectés.
    """
    async with config_pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE index_jobs
            SET status         = 'error',
                error_message  = 'stale_at_boot',
                finished_at    = now(),
                duration_ms    = CASE
                    WHEN started_at IS NOT NULL THEN
                        EXTRACT(MILLISECONDS FROM (now() - started_at))::int
                    ELSE 0
                END
            WHERE status = 'running'
            """
        )
    # asyncpg retourne "UPDATE N" — extraire N.
    count = int(result.split()[-1])
    if count > 0:
        log.warning("sync.recovery.reset_stale_running_jobs", count=count)
    return count
