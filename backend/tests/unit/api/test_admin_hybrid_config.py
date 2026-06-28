from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.api.admin import build_admin_router
from rag.auth.admin_auth import require_admin


def _app_with_pool(pool: MagicMock) -> FastAPI:
    app = FastAPI()
    app.state.pools = MagicMock()
    app.state.pools.config_pool = pool
    admin_router = build_admin_router()
    app.include_router(admin_router, prefix="/admin")
    app.dependency_overrides[require_admin] = lambda: None
    return app


class TestGetHybridConfig:
    def test_returns_404_when_no_config(self):
        ws_id = uuid4()
        pool = MagicMock()
        pool.fetchrow = AsyncMock(
            side_effect=[
                {"id": ws_id},   # workspace lookup
                None,            # hybrid_configs lookup → absent
            ]
        )
        client = TestClient(_app_with_pool(pool))
        resp = client.get("/admin/workspaces/myws/hybrid-config")
        assert resp.status_code == 404

    def test_returns_config_when_exists(self):
        ws_id = uuid4()
        pool = MagicMock()
        pool.fetchrow = AsyncMock(
            side_effect=[
                {"id": ws_id},
                {
                    "workspace_id": ws_id,
                    "enabled": True,
                    "rrf_k": 60,
                    "fts_config": "simple",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                },
            ]
        )
        client = TestClient(_app_with_pool(pool))
        resp = client.get("/admin/workspaces/myws/hybrid-config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["rrf_k"] == 60
        assert data["fts_config"] == "simple"


class TestPutHybridConfig:
    def test_upsert_returns_200(self):
        ws_id = uuid4()
        pool = MagicMock()
        pool.fetchrow = AsyncMock(
            side_effect=[
                {"id": ws_id},   # workspace lookup
                {
                    "workspace_id": ws_id,
                    "enabled": True,
                    "rrf_k": 30,
                    "fts_config": "french",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-02T00:00:00Z",
                },
            ]
        )
        pool.execute = AsyncMock()
        client = TestClient(_app_with_pool(pool))
        resp = client.put(
            "/admin/workspaces/myws/hybrid-config",
            json={"enabled": True, "rrf_k": 30, "fts_config": "french"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["rrf_k"] == 30

    def test_upsert_returns_404_when_workspace_missing(self):
        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value=None)
        client = TestClient(_app_with_pool(pool))
        resp = client.put(
            "/admin/workspaces/noexist/hybrid-config",
            json={"enabled": True, "rrf_k": 60, "fts_config": "simple"},
        )
        assert resp.status_code == 404
