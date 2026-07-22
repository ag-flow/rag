"""Émission d'un event applicatif → outbox (fire-and-forget, at-least-once).

À appeler par le code métier APRÈS le succès de l'opération. Ne fait qu'un
INSERT dans l'outbox (aucun réseau), gouverné par la config à chaud (enabled +
liste blanche). Ne lève JAMAIS vers l'appelant : un event non relayé ne doit
pas casser l'opération métier.
"""

from __future__ import annotations

import asyncpg
import structlog

from rag.db import workflow_outbox
from rag.events.config import get_config
from rag.events.envelope import serialize, to_envelope
from rag.events.registry import AppEvent

log = structlog.get_logger(__name__)


async def emit_workflow_event(config_pool: asyncpg.Pool, event: AppEvent) -> None:
    """Enfile l'event dans l'outbox s'il est relayé. Silencieux sur erreur."""
    try:
        async with config_pool.acquire() as conn:
            cfg = await get_config(conn)
            if not cfg.relays(event.event_code):
                return
            raw = serialize(to_envelope(event, source_uri=cfg.source_uri))
            async with conn.transaction():
                await workflow_outbox.enqueue(conn, event_code=event.event_code, payload=raw)
        log.info("workflow.event.enqueued", event_code=event.event_code)
    except Exception:
        # At-least-once best-effort : ne jamais faire échouer le métier.
        log.warning("workflow.event.enqueue_failed", event_code=event.event_code, exc_info=True)
