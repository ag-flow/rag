from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from rag.main import build_app
from rag.secrets.resolver import SecretResolver

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest_asyncio.fixture
async def test_app_client(pg_container: str) -> AsyncIterator[TestClient]:
    # pg_container est function-scope (DB jetable par test) → on doit forcer
    # l'assignment et non `setdefault`, sinon DATABASE_URL pointe vers la base
    # du test précédent (déjà droppée).
    os.environ["DATABASE_URL"] = pg_container
    os.environ["RAG_POSTGRES_ADMIN_URL"] = pg_container
    os.environ.setdefault("RAG_MASTER_KEY", "mk_test_xyz_padding_padding_padding_padding")
    os.environ.setdefault("RAG_PUBLIC_URL", "http://localhost:8000")
    os.environ.setdefault("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_stub")
    os.environ.setdefault("HARPOCRATE_API_URL_RAG", "https://vault.example.com")
    os.environ.setdefault("ENVIRONMENT", "dev")

    app = build_app(
        version="0.1.0",
        git_sha="testsha",
        resolver_factory=lambda _cfg, _app: SecretResolver(harpocrate_clients={}),
        migrations_dir=_MIGRATIONS_DIR,
    )

    with TestClient(app) as client:
        yield client


@pytest.mark.asyncio
async def test_app_boots_and_health_responds(test_app_client: TestClient) -> None:
    r = test_app_client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_app_version_response(test_app_client: TestClient) -> None:
    r = test_app_client.get("/version")
    body = r.json()
    assert body["version"] == "0.1.0"
    assert body["git"] == "testsha"
