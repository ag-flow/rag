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
async def admin_client(pg_container: str) -> AsyncIterator[TestClient]:
    os.environ["DATABASE_URL"] = pg_container
    os.environ["RAG_POSTGRES_ADMIN_URL"] = pg_container.rsplit("/", 1)[0] + "/postgres"
    os.environ.setdefault("RAG_MASTER_KEY", "mk_test_xyz")
    os.environ.setdefault("RAG_PUBLIC_URL", "http://localhost:8000")
    os.environ.setdefault("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_stub")
    os.environ.setdefault("HARPOCRATE_API_URL_RAG", "https://vault.example.com")
    os.environ.setdefault("ENVIRONMENT", "dev")

    app = build_app(
        version="0.2.0",
        git_sha="testsha",
        resolver_factory=lambda _cfg: SecretResolver(harpocrate_clients={}),
        migrations_dir=_MIGRATIONS_DIR,
    )
    with TestClient(app) as client:
        yield client


def test_admin_routes_require_master_key(admin_client: TestClient) -> None:
    r = admin_client.get("/workspaces")
    assert r.status_code == 401
    assert r.json()["detail"] == "missing_bearer_token"


def test_admin_routes_accept_valid_master_key(admin_client: TestClient) -> None:
    r = admin_client.get(
        "/workspaces", headers={"Authorization": "Bearer mk_test_xyz"}
    )
    assert r.status_code == 200
    assert r.json() == []


def test_admin_error_handlers_registered(admin_client: TestClient) -> None:
    r = admin_client.get(
        "/workspaces/absent", headers={"Authorization": "Bearer mk_test_xyz"}
    )
    assert r.status_code == 404
    assert r.json() == {"error": "workspace_not_found", "name": "absent"}
