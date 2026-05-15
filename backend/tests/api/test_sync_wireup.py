from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from fastapi.testclient import TestClient

from rag.main import build_app
from rag.secrets.resolver import SecretResolver

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest_asyncio.fixture
async def wired_client(pg_container: str, tmp_path: Path) -> AsyncIterator[TestClient]:
    os.environ["DATABASE_URL"] = pg_container
    os.environ["RAG_POSTGRES_ADMIN_URL"] = pg_container.rsplit("/", 1)[0] + "/postgres"
    os.environ.setdefault("RAG_MASTER_KEY", "mk_test_sync")
    os.environ.setdefault("RAG_PUBLIC_URL", "http://localhost:8000")
    os.environ.setdefault("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_stub")
    os.environ.setdefault("HARPOCRATE_API_URL_RAG", "https://vault.example.com")
    os.environ.setdefault("ENVIRONMENT", "dev")
    os.environ["SYNC_REPOS_ROOT"] = str(tmp_path / "repos")
    os.environ["SYNC_WORKER_POLL_INTERVAL_SECONDS"] = "1"

    app = build_app(
        version="0.3.0",
        git_sha="testsha",
        resolver_factory=lambda _cfg: SecretResolver(harpocrate_clients={}),
        migrations_dir=_MIGRATIONS_DIR,
    )
    with TestClient(app) as client:
        yield client


def test_sync_worker_attached_to_app_state(wired_client: TestClient) -> None:
    """Après lifespan startup, app.state.sync_worker doit exister."""
    app = wired_client.app
    assert hasattr(app.state, "sync_worker")
    assert app.state.sync_worker is not None


def test_health_responds_after_wireup(wired_client: TestClient) -> None:
    """Le lifespan complet (recovery + worker start) ne casse pas /health."""
    r = wired_client.get("/health")
    assert r.status_code == 200
