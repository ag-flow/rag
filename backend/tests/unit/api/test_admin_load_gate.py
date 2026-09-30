"""GET /api/admin/load-gate expose la pause effective du worker, distincte du
verdict instantané du gate — une pause qui dure doit se voir dans l'IHM."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.api.admin_load_gate import build_admin_load_gate_router
from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.services.load_gate import LoadGateStatus


def _status() -> LoadGateStatus:
    return LoadGateStatus(
        enabled=True,
        overloaded=True,
        cpu_psi_avg60=2.0,
        memory_used_pct=85.4,
        memory_source="meminfo",
        io_psi_avg60=None,
        cpu_threshold_pct=40,
        memory_threshold_pct=85,
        io_threshold_pct=60,
        reasons=["memory 85.4 > 85%"],
    )


def _client(worker: object | None) -> TestClient:
    app = FastAPI()
    app.state.load_gate = SimpleNamespace(status=_status)
    if worker is not None:
        app.state.sync_worker = worker
    app.include_router(build_admin_load_gate_router(), prefix="/api/admin")
    app.dependency_overrides[require_master_key_or_authenticated_admin] = lambda: None
    return TestClient(app)


def test_exposes_worker_pause_start() -> None:
    since = datetime(2026, 9, 20, 11, 53, 4, tzinfo=UTC)
    resp = _client(SimpleNamespace(gate_paused_since=since)).get("/api/admin/load-gate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["overloaded"] is True
    assert datetime.fromisoformat(body["worker_paused_since"]) == since
    assert body["memory_source"] == "meminfo"


def test_worker_not_paused() -> None:
    resp = _client(SimpleNamespace(gate_paused_since=None)).get("/api/admin/load-gate")
    assert resp.json()["worker_paused_since"] is None


def test_no_worker_attached() -> None:
    resp = _client(None).get("/api/admin/load-gate")
    assert resp.json()["worker_paused_since"] is None
