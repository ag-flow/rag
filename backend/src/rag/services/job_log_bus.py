from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any


class JobLogBus:
    """Bus d'événements en mémoire pour diffuser les logs de sync en temps réel.

    Chaque job dispose d'un buffer (max 500 événements) pour replay aux
    abonnés qui se connectent après le début du job. Le buffer et le flag
    `done` sont évincés un délai après complétion (BUG-063) : ça laisse le
    temps aux subscribers tardifs de récupérer le replay_buffer sans pour
    autant retenir indéfiniment la mémoire du process.
    """

    _BUFFER_MAX = 500
    _EVICTION_DELAY_SECONDS = 300

    def __init__(self) -> None:
        self._buffers: dict[str, list[dict[str, Any]]] = {}
        self._waiters: dict[str, list[asyncio.Queue[dict[str, Any] | None]]] = {}
        self._done: set[str] = set()
        self._eviction_handles: dict[str, asyncio.TimerHandle] = {}

    def publish(self, job_id: str, level: str, msg: str) -> None:
        event: dict[str, Any] = {
            "type": "log",
            "level": level,
            "msg": msg,
            "ts": datetime.now(UTC).isoformat(),
        }
        buf = self._buffers.setdefault(job_id, [])
        if len(buf) < self._BUFFER_MAX:
            buf.append(event)
        for q in self._waiters.get(job_id, []):
            q.put_nowait(event)

    def complete(
        self,
        job_id: str,
        *,
        status: str,
        files_changed: int = 0,
        files_skipped: int = 0,
    ) -> None:
        event: dict[str, Any] = {
            "type": "done",
            "status": status,
            "files_changed": files_changed,
            "files_skipped": files_skipped,
        }
        buf = self._buffers.setdefault(job_id, [])
        if len(buf) < self._BUFFER_MAX:
            buf.append(event)
        for q in self._waiters.pop(job_id, []):
            q.put_nowait(event)
        self._done.add(job_id)
        self._schedule_eviction(job_id)

    def _schedule_eviction(self, job_id: str) -> None:
        """Planifie la libération du buffer/flag `done` de `job_id` après
        `_EVICTION_DELAY_SECONDS`, le temps que les subscribers tardifs
        récupèrent le replay_buffer."""
        existing = self._eviction_handles.pop(job_id, None)
        if existing is not None:
            existing.cancel()
        loop = asyncio.get_running_loop()
        handle = loop.call_later(self._EVICTION_DELAY_SECONDS, self._evict, job_id)
        self._eviction_handles[job_id] = handle

    def _evict(self, job_id: str) -> None:
        self._buffers.pop(job_id, None)
        self._done.discard(job_id)
        self._waiters.pop(job_id, None)
        self._eviction_handles.pop(job_id, None)

    def subscribe(
        self, job_id: str
    ) -> tuple[list[dict[str, Any]], asyncio.Queue[dict[str, Any] | None]]:
        """Retourne (replay_buffer, queue). Le buffer contient les événements passés."""
        replay = list(self._buffers.get(job_id, []))
        q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        if job_id not in self._done:
            self._waiters.setdefault(job_id, []).append(q)
        return replay, q

    def unsubscribe(self, job_id: str, q: asyncio.Queue[dict[str, Any] | None]) -> None:
        subs = self._waiters.get(job_id, [])
        with contextlib.suppress(ValueError):
            subs.remove(q)
