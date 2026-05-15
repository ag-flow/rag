from __future__ import annotations

import json

import asyncpg
import structlog

log = structlog.get_logger(__name__)


async def schedule_due_sources(
    config_pool: asyncpg.Pool,
    *,
    default_interval_seconds: int,
) -> int:
    """Crée des jobs `pending` pour les sources dont `next_sync_at <= now()`
    et qui n'ont pas déjà un job `pending` ou `running` ouvert.

    Pour chaque source schedulée :
      - INSERT `index_jobs (triggered_by='schedule', status='pending')`
      - UPDATE `workspace_sources.next_sync_at = now() + interval`
        où `interval = config.sync_interval_seconds` ou `default_interval_seconds`.

    Retourne le nombre de sources schedulées.
    """
    async with config_pool.acquire() as conn, conn.transaction():
        due = await conn.fetch(
            """
            SELECT s.id AS source_id, s.workspace_id, s.config
            FROM workspace_sources s
            WHERE s.next_sync_at IS NOT NULL
              AND s.next_sync_at <= now()
              AND NOT EXISTS (
                  SELECT 1 FROM index_jobs j
                  WHERE j.source_id = s.id
                    AND j.status IN ('pending', 'running')
              )
            ORDER BY s.next_sync_at
            LIMIT 100
            FOR UPDATE SKIP LOCKED
            """
        )
        n = 0
        for row in due:
            interval = _extract_interval(row["config"], default_interval_seconds)
            await conn.execute(
                """
                INSERT INTO index_jobs (workspace_id, source_id, triggered_by, status)
                VALUES ($1, $2, 'schedule', 'pending')
                """,
                row["workspace_id"],
                row["source_id"],
            )
            await conn.execute(
                """
                UPDATE workspace_sources
                SET next_sync_at = now() + ($1 || ' seconds')::interval
                WHERE id = $2
                """,
                str(interval),
                row["source_id"],
            )
            n += 1
    if n > 0:
        log.info("sync.scheduler.scheduled", count=n)
    return n


def _extract_interval(config: object, default_seconds: int) -> int:
    """Lit `sync_interval_seconds` dans le JSONB de la source (clé optionnelle).

    asyncpg retourne le jsonb sous forme de `str` (pas de codec configuré
    sur le pool de test/prod). On parse en `dict` si nécessaire, suivant le
    pattern existant dans `services/sources.py::_source_to_dict`.
    """
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except (ValueError, TypeError):
            return default_seconds
    if isinstance(config, dict):
        val = config.get("sync_interval_seconds")
        if isinstance(val, int) and val >= 60:
            return val
    return default_seconds
