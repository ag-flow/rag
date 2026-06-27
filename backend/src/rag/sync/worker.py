from __future__ import annotations

import asyncio
import contextlib
from typing import Protocol

import asyncpg
import structlog

from rag.indexer.protocol import IndexerProtocol
from rag.services.job_log_bus import JobLogBus
from rag.sync.executor import execute_next_pending_job
from rag.sync.repo_storage import RepoStorage
from rag.sync.scheduler import schedule_due_sources

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


class _ClientProviderProtocol(Protocol):
    async def get_default_vault_name(self) -> str | None: ...


class SyncWorker:
    """Worker asyncio géré par le lifespan FastAPI.

    Boucle infinie qui réveille toutes les `poll_interval_seconds` :
      1. schedule_due_sources(...) → INSERT jobs pour les sources dues
      2. execute_next_pending_job(...) → picke 1 job, exécute, transition
      3. asyncio.sleep(poll_interval_seconds)

    Lifecycle :
      - `await worker.start()` lance la task.
      - `await worker.stop()` set un Event d'arrêt et await la task (avec
        timeout pour éviter les hang). Idempotent.

    Single replica : la sub-query `NOT EXISTS pending|running` du scheduler
    + `FOR UPDATE SKIP LOCKED` du picker rendent multi-worker safe en théorie,
    mais M3 reste single-task.
    """

    def __init__(
        self,
        *,
        config_pool: asyncpg.Pool,
        storage: RepoStorage,
        indexer: IndexerProtocol,
        resolver: _ResolverProtocol,
        client_provider: _ClientProviderProtocol,
        poll_interval_seconds: int,
        default_sync_interval_seconds: int,
        job_log_bus: JobLogBus | None = None,
        webhook_secret: str | None = None,
    ) -> None:
        self._config_pool = config_pool
        self._storage = storage
        self._indexer = indexer
        self._resolver = resolver
        self._client_provider = client_provider
        self._poll_interval = poll_interval_seconds
        self._default_sync_interval = default_sync_interval_seconds
        self._job_log_bus = job_log_bus
        self._webhook_secret = webhook_secret
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Démarre la task de fond. No-op si déjà démarrée."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="sync-worker")
        log.info("sync.worker.started", poll_interval=self._poll_interval)

    async def stop(self, *, stop_timeout: float = 10.0) -> None:
        """Demande l'arrêt et attend la task. Idempotent."""
        self._stop_event.set()
        if self._task is None:
            return
        try:
            await asyncio.wait_for(self._task, timeout=stop_timeout)
        except TimeoutError:
            log.warning("sync.worker.stop_timeout")
            self._task.cancel()
        finally:
            self._task = None
            log.info("sync.worker.stopped")

    async def _run(self) -> None:
        """Boucle principale. Catch toutes les exceptions de cycle pour
        ne pas tuer le worker — chaque cycle est isolé.
        """
        from rag.services.webhooks import purge_old_webhook_calls

        while not self._stop_event.is_set():
            try:
                await schedule_due_sources(
                    self._config_pool,
                    default_interval_seconds=self._default_sync_interval,
                )
                await execute_next_pending_job(
                    config_pool=self._config_pool,
                    storage=self._storage,
                    indexer=self._indexer,
                    resolver=self._resolver,
                    client_provider=self._client_provider,
                    job_log_bus=self._job_log_bus,
                    webhook_secret=self._webhook_secret,
                )
                try:
                    await purge_old_webhook_calls(self._config_pool)
                except Exception:
                    log.warning("sync.worker.purge_webhook_calls_failed")
                try:
                    from rag.services.circuit_breaker import auto_close_expired_circuits
                    await auto_close_expired_circuits(self._config_pool)
                except Exception:
                    log.warning("sync.worker.circuit_breaker_cleanup_failed")
            except Exception:
                log.exception("sync.worker.cycle_error")

            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._poll_interval,
                )
