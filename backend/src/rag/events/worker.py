"""Worker de fond du producteur d'events (livraison hors transaction, retry/backoff).

Géré par le lifespan FastAPI, façon SyncWorker : toutes les ~`poll_interval`
secondes, réclame les lignes dues, signe + POST chacune HORS transaction DB,
puis marque le résultat (delivered / retry avec backoff / failed). Purge les
livrés périodiquement.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Protocol

import asyncpg
import httpx
import structlog

from rag.db import workflow_outbox
from rag.events.config import get_config
from rag.events.egress import deliver

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


class WorkflowEventsWorker:
    """Task asyncio de livraison de l'outbox vers workflow."""

    def __init__(
        self,
        *,
        config_pool: asyncpg.Pool,
        resolver: _ResolverProtocol,
        poll_interval_seconds: int = 10,
    ) -> None:
        self._config_pool = config_pool
        self._resolver = resolver
        self._poll_interval = poll_interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="workflow-events-worker")
        log.info("workflow.events.worker.started", poll_interval=self._poll_interval)

    async def stop(self, *, stop_timeout: float = 10.0) -> None:
        self._stop.set()
        if self._task is None:
            return
        try:
            await asyncio.wait_for(self._task, timeout=stop_timeout)
        except TimeoutError:
            log.warning("workflow.events.worker.stop_timeout")
            self._task.cancel()
        finally:
            self._task = None
            log.info("workflow.events.worker.stopped")

    async def _run(self) -> None:
        async with httpx.AsyncClient() as client:
            while not self._stop.is_set():
                try:
                    await self._drain_once(client)
                except Exception:
                    log.warning("workflow.events.worker.cycle_failed", exc_info=True)
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=self._poll_interval)

    async def _drain_once(self, client: httpx.AsyncClient) -> None:
        async with self._config_pool.acquire() as conn:
            cfg = await get_config(conn)
        if not cfg.is_deliverable():
            return  # relais non configuré : on laisse les lignes en attente
        secret = await self._resolver.resolve_with_retry(cfg.secret_ref)

        # 1) réclame les lignes dues — transaction COURTE, refermée aussitôt.
        async with self._config_pool.acquire() as conn, conn.transaction():
            due = await workflow_outbox.claim_due(conn, limit=20)

        # 2) livraison HORS de toute transaction DB (piège : un POST lent
        #    tiendrait un verrou/une connexion). Marquage ensuite, transaction
        #    courte par entrée. At-least-once : un rejeu est dédupliqué par
        #    workflow (_eventId déterministe).
        for entry in due:
            if self._stop.is_set():
                return
            result = await deliver(
                client,
                base_url=cfg.workflow_base_url,
                source_id=cfg.source_id,
                secret=secret,
                raw_body=bytes(entry.payload),
            )
            async with self._config_pool.acquire() as conn, conn.transaction():
                if result.delivered:
                    await workflow_outbox.mark_delivered(conn, entry_id=entry.id)
                elif entry.attempts + 1 >= workflow_outbox.MAX_ATTEMPTS:
                    await workflow_outbox.mark_failed(conn, entry_id=entry.id, error=result.detail)
                    log.warning(
                        "workflow.event.failed", event_code=entry.event_code, detail=result.detail
                    )
                else:
                    await workflow_outbox.mark_retry(
                        conn, entry_id=entry.id, attempts=entry.attempts, error=result.detail
                    )

        # 3) purge des livrés anciens (best-effort).
        with contextlib.suppress(Exception):
            async with self._config_pool.acquire() as conn:
                await workflow_outbox.purge_delivered(conn)
