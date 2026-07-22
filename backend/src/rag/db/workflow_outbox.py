"""Outbox transactionnel des events workflow — livraison exactement-une-fois côté producteur.

Le code métier n'insère que l'enveloppe (octets exacts) ici, dans sa propre
transaction courte ; le worker de fond lit les lignes dues, POST hors
transaction, puis marque le résultat. Aucun réseau dans une transaction DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import asyncpg

# Backoff : 30·2^attempts, plafonné à 1 h ; abandon au-delà de MAX_ATTEMPTS.
_BACKOFF_BASE_SECONDS = 30
_BACKOFF_CAP_SECONDS = 3600
MAX_ATTEMPTS = 8


@dataclass(frozen=True)
class OutboxEntry:
    id: UUID
    event_code: str
    payload: bytes
    attempts: int


async def enqueue(conn: asyncpg.Connection, *, event_code: str, payload: bytes) -> UUID:
    """Insère une enveloppe à livrer. INSERT seul — appelé dans une transaction courte."""
    return await conn.fetchval(
        "INSERT INTO workflow_event_outbox (event_code, payload) VALUES ($1, $2) RETURNING id",
        event_code,
        payload,
    )


async def claim_due(conn: asyncpg.Connection, *, limit: int = 20) -> list[OutboxEntry]:
    """Verrouille et retourne les lignes dues (pending, échéance atteinte)."""
    rows = await conn.fetch(
        """
        SELECT id, event_code, payload, attempts
        FROM workflow_event_outbox
        WHERE status = 'pending' AND next_attempt_at <= now()
        ORDER BY next_attempt_at
        FOR UPDATE SKIP LOCKED
        LIMIT $1
        """,
        limit,
    )
    return [
        OutboxEntry(
            id=r["id"], event_code=r["event_code"], payload=r["payload"], attempts=r["attempts"]
        )
        for r in rows
    ]


async def mark_delivered(conn: asyncpg.Connection, *, entry_id: UUID) -> None:
    await conn.execute(
        "UPDATE workflow_event_outbox SET status='delivered', delivered_at=now(), "
        "attempts=attempts+1 WHERE id=$1",
        entry_id,
    )


async def mark_retry(
    conn: asyncpg.Connection, *, entry_id: UUID, attempts: int, error: str
) -> None:
    """Replanifie avec backoff exponentiel plafonné."""
    delay = min(_BACKOFF_BASE_SECONDS * (2**attempts), _BACKOFF_CAP_SECONDS)
    await conn.execute(
        "UPDATE workflow_event_outbox SET attempts=attempts+1, last_error=$2, "
        "next_attempt_at = now() + make_interval(secs => $3) WHERE id=$1",
        entry_id,
        error,
        delay,
    )


async def mark_failed(conn: asyncpg.Connection, *, entry_id: UUID, error: str) -> None:
    await conn.execute(
        "UPDATE workflow_event_outbox SET status='failed', attempts=attempts+1, last_error=$2 "
        "WHERE id=$1",
        entry_id,
        error,
    )


async def purge_delivered(conn: asyncpg.Connection, *, older_than_hours: int = 24) -> int:
    """Supprime les lignes livrées depuis plus de `older_than_hours`. Retourne le compte."""
    result = await conn.execute(
        "DELETE FROM workflow_event_outbox WHERE status='delivered' "
        "AND delivered_at < now() - make_interval(hours => $1)",
        older_than_hours,
    )
    return int(result.split()[-1]) if result.startswith("DELETE") else 0
