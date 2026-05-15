from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from rag.main import build_app
from rag.secrets.resolver import SecretResolver

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest_asyncio.fixture
async def wired_client(
    pg_container: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[TestClient]:
    # monkeypatch.setenv restaure les env vars au teardown — sans ça
    # SYNC_REPOS_ROOT et SYNC_WORKER_POLL_INTERVAL_SECONDS leakent
    # vers tests/unit/test_config.py qui s'appuie sur des defaults vierges.
    monkeypatch.setenv("DATABASE_URL", pg_container)
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", pg_container.rsplit("/", 1)[0] + "/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_sync")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_stub")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://vault.example.com")
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("SYNC_REPOS_ROOT", str(tmp_path / "repos"))
    monkeypatch.setenv("SYNC_WORKER_POLL_INTERVAL_SECONDS", "1")

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


def test_sync_worker_uses_real_indexer_not_noop(wired_client: TestClient) -> None:
    """Après M4a : l'indexer injecté au SyncWorker doit être RealIndexer."""
    from rag.indexer.real import RealIndexer

    app = wired_client.app
    worker = app.state.sync_worker
    # On accède au `_indexer` privé du worker - pas idéal mais nécessaire
    # pour valider l'injection sans exposer l'attribut publiquement.
    assert isinstance(worker._indexer, RealIndexer), (
        f"Expected RealIndexer, got {type(worker._indexer).__name__}"
    )
