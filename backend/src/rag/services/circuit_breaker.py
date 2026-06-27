from __future__ import annotations

import datetime
from typing import Any
from uuid import UUID

import asyncpg
import structlog

log = structlog.get_logger(__name__)

_DEFAULT_TTL_SECONDS = 3600  # 1 heure


async def open_circuit(
    pool: asyncpg.Pool,
    *,
    workspace_id: UUID,
    provider: str,
    model: str,
    error_message: str,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> None:
    """Ouvre (ou ré-ouvre) le circuit breaker d'un workspace.

    Idempotent : si un circuit est déjà ouvert, met à jour le message et
    prolonge open_until.
    """
    open_until = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        seconds=ttl_seconds
    )
    await pool.execute(
        """
        INSERT INTO indexer_circuit_breakers
            (workspace_id, provider, model, error_message, opened_at, open_until)
        VALUES ($1, $2, $3, $4, now(), $5)
        ON CONFLICT (workspace_id) DO UPDATE
        SET provider      = EXCLUDED.provider,
            model         = EXCLUDED.model,
            error_message = EXCLUDED.error_message,
            opened_at     = now(),
            open_until    = EXCLUDED.open_until
        """,
        workspace_id,
        provider,
        model,
        error_message,
        open_until,
    )
    log.warning(
        "circuit_breaker.opened",
        workspace_id=str(workspace_id),
        provider=provider,
        model=model,
        open_until=open_until.isoformat(),
    )


async def close_circuit(pool: asyncpg.Pool, *, workspace_id: UUID) -> bool:
    """Ferme le circuit breaker manuellement. Retourne True si un circuit
    existait, False s'il n'y avait rien à fermer.
    """
    result = await pool.execute(
        "DELETE FROM indexer_circuit_breakers WHERE workspace_id=$1",
        workspace_id,
    )
    closed = result != "DELETE 0"
    if closed:
        log.info("circuit_breaker.closed_manually", workspace_id=str(workspace_id))
    return closed


async def get_circuit(
    pool: asyncpg.Pool, *, workspace_id: UUID
) -> dict[str, Any] | None:
    """Retourne l'état du circuit breaker, ou None si fermé."""
    row = await pool.fetchrow(
        "SELECT * FROM indexer_circuit_breakers WHERE workspace_id=$1",
        workspace_id,
    )
    return dict(row) if row else None


async def auto_close_expired_circuits(pool: asyncpg.Pool) -> int:
    """Supprime les circuits dont open_until est dépassé. Retourne le nombre
    de circuits fermés automatiquement.
    """
    result = await pool.execute(
        """
        DELETE FROM indexer_circuit_breakers
        WHERE open_until IS NOT NULL AND open_until <= now()
        """
    )
    n = int(result.split()[-1])
    if n > 0:
        log.info("circuit_breaker.auto_closed", count=n)
    return n
