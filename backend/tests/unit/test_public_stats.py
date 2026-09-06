"""GET /api/public/stats (feature 2ca3ceb8) : compteurs d'accueil de l'écran
de connexion — sans auth, fail-soft si la base est indisponible."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.api.health import build_health_router


def _app(fetchrow: AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(build_health_router())
    app.state.pools = SimpleNamespace(config_pool=SimpleNamespace(fetchrow=fetchrow))
    return app


def test_counts_returned() -> None:
    fetchrow = AsyncMock(return_value={"documents": 42, "workspaces": 3})
    client = TestClient(_app(fetchrow))
    resp = client.get("/api/public/stats")
    assert resp.status_code == 200
    assert resp.json() == {"indexed_documents": 42, "workspaces": 3}


def test_database_down_fails_soft() -> None:
    fetchrow = AsyncMock(side_effect=RuntimeError("db down"))
    client = TestClient(_app(fetchrow))
    resp = client.get("/api/public/stats")
    assert resp.status_code == 200
    assert resp.json() == {"indexed_documents": None, "workspaces": None}
