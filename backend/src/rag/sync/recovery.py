from __future__ import annotations

import asyncpg
import structlog

log = structlog.get_logger(__name__)


async def reset_stale_running_jobs(config_pool: asyncpg.Pool) -> int:
    """Récupère tous les jobs `running` au boot (crash recovery).

    Un job `running` au démarrage signifie que le worker a crashé entre
    `started_at` et `finished_at`.

    Les jobs `push`/`delete` sont remis `pending` : leur ligne de payload
    (`push_job_payloads`/`delete_job_payloads`) survit au crash et n'est
    jamais purgée hors du `finally` normal de l'executor, donc un retry
    naturel est à la fois possible et nécessaire pour ne pas perdre le
    document (le hash-skip / la suppression par path protègent des
    doublons). Les autres jobs (git : schedule/manual/webhook/reindex_*)
    sont marqués `error`, ce qui libère la source pour un retry naturel
    au prochain cycle planifié.

    Retourne le nombre de jobs affectés (toutes catégories confondues).
    """
    async with config_pool.acquire() as conn, conn.transaction():
        pending_result = await conn.execute(
            """
            UPDATE index_jobs
            SET status       = 'pending',
                started_at   = NULL,
                retry_count  = retry_count + 1,
                retry_after  = NULL
            WHERE status = 'running'
              AND triggered_by IN ('push', 'delete')
            """
        )
        error_result = await conn.execute(
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
              AND triggered_by NOT IN ('push', 'delete')
            """
        )
    # asyncpg retourne "UPDATE N" — extraire N.
    pending_count = int(pending_result.split()[-1])
    error_count = int(error_result.split()[-1])
    count = pending_count + error_count
    if count > 0:
        log.warning(
            "sync.recovery.reset_stale_running_jobs",
            count=count,
            requeued_push_delete=pending_count,
            errored=error_count,
        )
    return count
