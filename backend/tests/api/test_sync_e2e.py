from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from fastapi.testclient import TestClient

from rag.main import build_app
from tests.integration._git_fixture import make_bare_repo_with_commits

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _AcceptAllResolver:
    def resolve_with_retry(self, ref: str) -> str:
        return "tok-x"


@pytest_asyncio.fixture
async def e2e_client(
    pg_container: str,
    tmp_path: Path,
) -> AsyncIterator[tuple[TestClient, Path]]:
    os.environ["DATABASE_URL"] = pg_container
    os.environ["RAG_POSTGRES_ADMIN_URL"] = pg_container.rsplit("/", 1)[0] + "/postgres"
    os.environ.setdefault("RAG_MASTER_KEY", "mk_test_e2e_sync")
    os.environ.setdefault("RAG_PUBLIC_URL", "http://localhost:8000")
    os.environ.setdefault("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_stub")
    os.environ.setdefault("HARPOCRATE_API_URL_RAG", "https://vault.example.com")
    os.environ.setdefault("ENVIRONMENT", "dev")
    os.environ["SYNC_REPOS_ROOT"] = str(tmp_path / "repos")
    os.environ["SYNC_WORKER_POLL_INTERVAL_SECONDS"] = "1"

    app = build_app(
        version="0.3.0",
        git_sha="testsha",
        resolver_factory=lambda _cfg: _AcceptAllResolver(),  # type: ignore[return-value]
        migrations_dir=_MIGRATIONS_DIR,
    )
    with TestClient(app) as client:
        yield client, tmp_path


def _bearer(value: str = "mk_test_e2e_sync") -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


def test_full_pipeline_create_workspace_source_reindex_done(
    e2e_client: tuple[TestClient, Path],
) -> None:
    """E2E complet : create workspace → add source pointant vers bare repo
    local → worker picke et exécute (next_sync_at=now() à la création) →
    job done dans /jobs."""
    client, tmp_path = e2e_client
    bare = make_bare_repo_with_commits(
        tmp_path,
        {"README.md": "hello", "docs/intro.md": "intro"},
    )

    # 1. Create workspace
    r = client.post(
        "/workspaces",
        headers=_bearer(),
        json={
            "name": "ws_e2e_sync",
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 201

    # 2. Add source (next_sync_at=now() → worker va picker au prochain cycle)
    r = client.post(
        "/workspaces/ws_e2e_sync/sources",
        headers=_bearer(),
        json={
            "type": "git",
            "config": {"url": f"file://{bare}", "branch": "main"},
        },
    )
    assert r.status_code == 201

    # 3. Attendre que le worker traite le job (poll_interval=1s, timeout 20s)
    deadline = time.time() + 20
    final_status = None
    while time.time() < deadline:
        jobs = client.get("/workspaces/ws_e2e_sync/jobs", headers=_bearer()).json()
        if jobs and jobs[0]["status"] in ("done", "error"):
            final_status = jobs[0]
            break
        time.sleep(0.5)

    assert final_status is not None, "Le job n'a pas été traité dans le délai imparti"
    assert final_status["status"] == "done", f"Job status: {final_status}"
    assert final_status["files_changed"] >= 1
