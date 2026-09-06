"""Worker parallèle multi-utilisateurs (feature a9719d13) : N slots globaux,
picks séquentiels, exécution en tasks concurrentes, plafond relu à chaud."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.sync import worker as worker_mod
from rag.sync.worker import SyncWorker


def _worker(max_jobs: int | None) -> SyncWorker:
    return SyncWorker(
        config_pool=MagicMock(),
        storage=MagicMock(),
        indexer=MagicMock(),
        resolver=MagicMock(),
        client_provider=MagicMock(),
        poll_interval_seconds=30,
        default_sync_interval_seconds=300,
        max_jobs_provider=(lambda: max_jobs) if max_jobs is not None else None,
    )


@pytest.fixture
def maintenance_mocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker_mod, "schedule_due_sources", AsyncMock())
    monkeypatch.setattr("rag.services.webhooks.purge_old_webhook_calls", AsyncMock(), raising=False)
    monkeypatch.setattr(
        "rag.services.circuit_breaker.auto_close_expired_circuits",
        AsyncMock(),
        raising=False,
    )


@pytest.mark.usefixtures("maintenance_mocks")
@pytest.mark.asyncio
async def test_two_jobs_run_concurrently(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avec 2 slots, le job de l'utilisateur B démarre PENDANT celui de A."""
    release = asyncio.Event()
    started: list[str] = []

    async def _blocking_execute(*, job: MagicMock, **_: object) -> None:
        started.append(job.job_id)
        await release.wait()

    monkeypatch.setattr(
        worker_mod,
        "pick_next_pending_job",
        AsyncMock(side_effect=[MagicMock(job_id="a"), MagicMock(job_id="b"), None]),
    )
    monkeypatch.setattr(worker_mod, "execute_picked_job", _blocking_execute)

    w = _worker(2)
    await w._cycle()
    await asyncio.sleep(0)  # laisse les tasks démarrer
    assert sorted(started) == ["a", "b"]
    assert w.active_jobs == 2
    release.set()
    await asyncio.gather(*w._job_tasks)
    assert w.active_jobs == 0


@pytest.mark.usefixtures("maintenance_mocks")
@pytest.mark.asyncio
async def test_max_jobs_caps_in_flight(monkeypatch: pytest.MonkeyPatch) -> None:
    """Slots pleins ⇒ plus aucun pick tant qu'un job n'est pas terminé."""
    release = asyncio.Event()

    async def _blocking_execute(**_: object) -> None:
        await release.wait()

    pick = AsyncMock(side_effect=[MagicMock(job_id="a"), MagicMock(job_id="b"), None])
    monkeypatch.setattr(worker_mod, "pick_next_pending_job", pick)
    monkeypatch.setattr(worker_mod, "execute_picked_job", _blocking_execute)

    w = _worker(1)
    await w._cycle()
    await w._cycle()  # slot occupé : pas de nouveau pick
    assert pick.await_count == 1
    release.set()
    await asyncio.gather(*w._job_tasks)
    await w._cycle()  # slot libéré : pick suivant
    assert pick.await_count == 2


@pytest.mark.usefixtures("maintenance_mocks")
@pytest.mark.asyncio
async def test_gate_rechecked_between_picks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le gate de charge est re-consulté avant CHAQUE pick du remplissage."""
    states = iter([False, True])
    gate = SimpleNamespace(status=lambda: SimpleNamespace(overloaded=next(states), reasons=["mem"]))
    release = asyncio.Event()

    async def _blocking_execute(**_: object) -> None:
        await release.wait()

    pick = AsyncMock(side_effect=[MagicMock(job_id="a"), MagicMock(job_id="b"), None])
    monkeypatch.setattr(worker_mod, "pick_next_pending_job", pick)
    monkeypatch.setattr(worker_mod, "execute_picked_job", _blocking_execute)

    w = SyncWorker(
        config_pool=MagicMock(),
        storage=MagicMock(),
        indexer=MagicMock(),
        resolver=MagicMock(),
        client_provider=MagicMock(),
        poll_interval_seconds=30,
        default_sync_interval_seconds=300,
        load_gate=gate,  # type: ignore[arg-type]
        max_jobs_provider=lambda: 4,
    )
    await w._cycle()
    assert pick.await_count == 1  # le 2e pick a été refusé par le gate
    release.set()
    await asyncio.gather(*w._job_tasks)


@pytest.mark.usefixtures("maintenance_mocks")
@pytest.mark.asyncio
async def test_failing_job_does_not_kill_other_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = asyncio.Event()
    done: list[str] = []

    async def _execute(*, job: MagicMock, **_: object) -> None:
        if job.job_id == "boom":
            raise RuntimeError("explode")
        await release.wait()
        done.append(job.job_id)

    monkeypatch.setattr(
        worker_mod,
        "pick_next_pending_job",
        AsyncMock(side_effect=[MagicMock(job_id="boom"), MagicMock(job_id="ok"), None]),
    )
    monkeypatch.setattr(worker_mod, "execute_picked_job", _execute)

    w = _worker(2)
    await w._cycle()
    release.set()
    await asyncio.gather(*w._job_tasks)
    assert done == ["ok"]


@pytest.mark.usefixtures("maintenance_mocks")
@pytest.mark.asyncio
async def test_invalid_provider_falls_back_to_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker_mod, "pick_next_pending_job", AsyncMock(return_value=None))
    monkeypatch.setattr(worker_mod, "execute_picked_job", AsyncMock())

    def _broken() -> int:
        raise RuntimeError("admin.env illisible")

    w = _worker(None)
    w._max_jobs_provider = _broken
    assert w._max_jobs() == 1
    assert _worker(0)._max_jobs() == 1
    assert _worker(None)._max_jobs() == 1
    assert _worker(3)._max_jobs() == 3
