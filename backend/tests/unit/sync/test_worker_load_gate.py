"""Le SyncWorker saute le pick de job quand le gate de charge est surchargé
(enabler 01f8992b) — le scheduling et les entretiens continuent."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from structlog.testing import capture_logs

from rag.services.load_gate import LoadGateStatus
from rag.sync import worker as worker_mod
from rag.sync.worker import SyncWorker


def _status(overloaded: bool) -> LoadGateStatus:
    return LoadGateStatus(
        enabled=True,
        overloaded=overloaded,
        cpu_psi_avg60=55.0 if overloaded else 5.0,
        memory_used_pct=40.0,
        memory_source="meminfo",
        io_psi_avg60=None,
        cpu_threshold_pct=40,
        memory_threshold_pct=85,
        io_threshold_pct=60,
        reasons=["cpu psi avg60 55.0 > 40%"] if overloaded else [],
    )


def _worker(gate: Any, clock: Any = None) -> SyncWorker:
    extra = {"clock": clock} if clock is not None else {}
    return SyncWorker(
        config_pool=MagicMock(),
        storage=MagicMock(),
        indexer=MagicMock(),
        resolver=MagicMock(),
        client_provider=MagicMock(),
        poll_interval_seconds=30,
        default_sync_interval_seconds=300,
        load_gate=gate,
        **extra,
    )


async def _drain(w: SyncWorker) -> None:
    if w._job_tasks:
        await asyncio.gather(*w._job_tasks)


@pytest.fixture
def cycle_mocks(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    mocks = SimpleNamespace(
        schedule=AsyncMock(),
        # Un job pickable puis file vide (le worker picke en boucle jusqu'à None).
        pick=AsyncMock(side_effect=[MagicMock(job_id="j1"), None, None, None]),
        execute=AsyncMock(),
    )
    monkeypatch.setattr(worker_mod, "schedule_due_sources", mocks.schedule)
    monkeypatch.setattr(worker_mod, "pick_next_pending_job", mocks.pick)
    monkeypatch.setattr(worker_mod, "execute_picked_job", mocks.execute)
    monkeypatch.setattr("rag.services.webhooks.purge_old_webhook_calls", AsyncMock(), raising=False)
    monkeypatch.setattr(
        "rag.services.circuit_breaker.auto_close_expired_circuits",
        AsyncMock(),
        raising=False,
    )
    return mocks


@pytest.mark.asyncio
async def test_overloaded_skips_job_pickup(cycle_mocks: SimpleNamespace) -> None:
    gate = SimpleNamespace(status=lambda: _status(True))
    w = _worker(gate)
    await w._cycle()
    await _drain(w)
    cycle_mocks.schedule.assert_awaited_once()  # le scheduling continue
    cycle_mocks.pick.assert_not_awaited()


@pytest.mark.asyncio
async def test_normal_load_picks_job(cycle_mocks: SimpleNamespace) -> None:
    gate = SimpleNamespace(status=lambda: _status(False))
    w = _worker(gate)
    await w._cycle()
    await _drain(w)
    cycle_mocks.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_gate_behaves_as_before(cycle_mocks: SimpleNamespace) -> None:
    w = _worker(None)
    await w._cycle()
    await _drain(w)
    cycle_mocks.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_pause_and_resume_transition(cycle_mocks: SimpleNamespace) -> None:
    states = iter([True, True, False])
    gate = SimpleNamespace(status=lambda: _status(next(states)))
    w = _worker(gate)
    await w._cycle()
    await w._cycle()
    await w._cycle()
    await _drain(w)
    # 2 cycles surchargés (0 pick), puis reprise (1 job exécuté).
    assert cycle_mocks.execute.await_count == 1
    assert w.gate_paused_since is None


class _Clock:
    """Horloge pilotable : avance à la demande, pas de sleep réel."""

    def __init__(self) -> None:
        self.now = datetime(2026, 9, 20, 11, 53, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


def _events(logs: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [e for e in logs if e["event"] == name]


@pytest.mark.asyncio
async def test_pause_records_start(cycle_mocks: SimpleNamespace) -> None:
    clock = _Clock()
    w = _worker(SimpleNamespace(status=lambda: _status(True)), clock)
    started = clock.now
    await w._cycle()
    clock.advance(30)
    await w._cycle()
    # Le début de pause est celui de la transition, pas du dernier cycle.
    assert w.gate_paused_since == started


@pytest.mark.asyncio
async def test_long_pause_logs_periodic_reminder(cycle_mocks: SimpleNamespace) -> None:
    clock = _Clock()
    w = _worker(SimpleNamespace(status=lambda: _status(True)), clock)
    with capture_logs() as logs:
        await w._cycle()
        clock.advance(worker_mod.PAUSE_REMINDER_SECONDS - 1)
        await w._cycle()
        clock.advance(1)
        await w._cycle()
        clock.advance(30)
        await w._cycle()
    assert len(_events(logs, "sync.worker.load_gate_paused")) == 1
    reminders = _events(logs, "sync.worker.load_gate_still_paused")
    assert len(reminders) == 1
    assert reminders[0]["paused_for_seconds"] == worker_mod.PAUSE_REMINDER_SECONDS
    assert reminders[0]["reasons"] == ["cpu psi avg60 55.0 > 40%"]


@pytest.mark.asyncio
async def test_resume_logs_pause_duration(cycle_mocks: SimpleNamespace) -> None:
    clock = _Clock()
    states = iter([True, False])
    w = _worker(SimpleNamespace(status=lambda: _status(next(states))), clock)
    with capture_logs() as logs:
        await w._cycle()
        clock.advance(120)
        await w._cycle()
        await _drain(w)
    resumed = _events(logs, "sync.worker.load_gate_resumed")
    assert len(resumed) == 1
    assert resumed[0]["paused_for_seconds"] == 120
    assert w.gate_paused_since is None
