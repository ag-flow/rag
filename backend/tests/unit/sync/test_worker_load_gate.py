"""Le SyncWorker saute le pick de job quand le gate de charge est surchargé
(enabler 01f8992b) — le scheduling et les entretiens continuent."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.services.load_gate import LoadGateStatus
from rag.sync import worker as worker_mod
from rag.sync.worker import SyncWorker


def _status(overloaded: bool) -> LoadGateStatus:
    return LoadGateStatus(
        enabled=True,
        overloaded=overloaded,
        cpu_psi_avg60=55.0 if overloaded else 5.0,
        memory_used_pct=40.0,
        cpu_threshold_pct=40,
        memory_threshold_pct=85,
        reasons=["cpu psi avg60 55.0 > 40%"] if overloaded else [],
    )


def _worker(gate: Any) -> SyncWorker:
    return SyncWorker(
        config_pool=MagicMock(),
        storage=MagicMock(),
        indexer=MagicMock(),
        resolver=MagicMock(),
        client_provider=MagicMock(),
        poll_interval_seconds=30,
        default_sync_interval_seconds=300,
        load_gate=gate,
    )


@pytest.fixture
def cycle_mocks(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    mocks = SimpleNamespace(
        schedule=AsyncMock(),
        execute=AsyncMock(),
    )
    monkeypatch.setattr(worker_mod, "schedule_due_sources", mocks.schedule)
    monkeypatch.setattr(worker_mod, "execute_next_pending_job", mocks.execute)
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
    await _worker(gate)._cycle()
    cycle_mocks.schedule.assert_awaited_once()  # le scheduling continue
    cycle_mocks.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_normal_load_picks_job(cycle_mocks: SimpleNamespace) -> None:
    gate = SimpleNamespace(status=lambda: _status(False))
    await _worker(gate)._cycle()
    cycle_mocks.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_gate_behaves_as_before(cycle_mocks: SimpleNamespace) -> None:
    await _worker(None)._cycle()
    cycle_mocks.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_pause_and_resume_transition(cycle_mocks: SimpleNamespace) -> None:
    states = iter([True, True, False])
    gate = SimpleNamespace(status=lambda: _status(next(states)))
    w = _worker(gate)
    await w._cycle()
    await w._cycle()
    await w._cycle()
    # 2 cycles surchargés (0 pick), puis reprise (1 pick).
    assert cycle_mocks.execute.await_count == 1
    assert w._gate_paused is False
