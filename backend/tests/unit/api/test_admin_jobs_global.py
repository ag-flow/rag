"""Endpoint GET /api/admin/jobs — liste globale cross-workspace des index_jobs.

Pool mocké (pattern test_admin_hybrid_config) : on vérifie la forme de la
réponse (workspace_name joint), les valeurs par défaut et le passage des
filtres `limit` / `workspace` / `status` au service.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.api.admin import build_admin_router
from rag.auth.admin_auth import require_admin


def _row(workspace_name: str, *, status: str = "done") -> dict[str, Any]:
    return {
        "id": uuid4(),
        "triggered_by": "manual",
        "status": status,
        "files_changed": 3,
        "files_skipped": 1,
        "error_message": None,
        "started_at": datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        "finished_at": None,
        "duration_ms": 1200,
        "workspace_name": workspace_name,
    }


def _client(rows: list[dict[str, Any]]) -> tuple[TestClient, AsyncMock]:
    fetch = AsyncMock(return_value=rows)
    conn = MagicMock()
    conn.fetch = fetch
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn

    app = FastAPI()
    app.state.pools = MagicMock()
    app.state.pools.config_pool = pool
    app.include_router(build_admin_router(), prefix="/api/admin")
    app.dependency_overrides[require_admin] = lambda: None
    return TestClient(app), fetch


class TestGetAllJobs:
    def test_renvoie_les_jobs_avec_workspace_name(self) -> None:
        client, _ = _client([_row("ws-a"), _row("ws-b", status="error")])

        resp = client.get("/api/admin/jobs")

        assert resp.status_code == 200
        data = resp.json()
        assert [j["workspace_name"] for j in data] == ["ws-a", "ws-b"]
        first = data[0]
        assert first["triggered_by"] == "manual"
        assert first["status"] == "done"
        assert first["files_changed"] == 3
        assert first["files_skipped"] == 1
        assert first["started_at"] == "2026-07-18T12:00:00+00:00"
        assert first["duration_ms"] == 1200

    def test_defauts_limit_50_sans_filtres(self) -> None:
        client, fetch = _client([])

        resp = client.get("/api/admin/jobs")

        assert resp.status_code == 200
        assert resp.json() == []
        # args = (query, workspace, status, limit)
        _query, workspace, status, limit = fetch.await_args.args
        assert workspace is None
        assert status is None
        assert limit == 50

    def test_filtres_workspace_et_status_transmis(self) -> None:
        client, fetch = _client([_row("ws-a", status="error")])

        resp = client.get("/api/admin/jobs?workspace=ws-a&status=error&limit=10")

        assert resp.status_code == 200
        _query, workspace, status, limit = fetch.await_args.args
        assert workspace == "ws-a"
        assert status == "error"
        assert limit == 10

    def test_limit_superieur_a_200_rejete(self) -> None:
        client, fetch = _client([])

        resp = client.get("/api/admin/jobs?limit=201")

        assert resp.status_code == 422
        fetch.assert_not_awaited()

    def test_limit_zero_rejete(self) -> None:
        client, fetch = _client([])

        resp = client.get("/api/admin/jobs?limit=0")

        assert resp.status_code == 422
        fetch.assert_not_awaited()

    def test_jointure_workspace_et_tri_created_at_desc_dans_le_sql(self) -> None:
        client, fetch = _client([])

        client.get("/api/admin/jobs")

        query = fetch.await_args.args[0]
        assert "JOIN workspaces w ON w.id = j.workspace_id" in query
        assert "ORDER BY j.created_at DESC" in query
