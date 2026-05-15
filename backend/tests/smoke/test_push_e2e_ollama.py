# backend/tests/smoke/test_push_e2e_ollama.py
from __future__ import annotations

import os

import asyncpg
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.smoke


@pytest.fixture
def ollama_url() -> str:
    url = os.environ.get("OLLAMA_TEST_URL")
    if not url:
        pytest.skip("OLLAMA_TEST_URL non défini — smoke push Ollama sauté.")
    return url


def test_push_e2e_indexes_embeddings_in_pgvector(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
    ollama_url: str,
) -> None:
    """End-to-end : crée un workspace Ollama, push 1 doc, vérifie pgvector."""
    # 1. Crée le workspace avec provider Ollama (pas d'api_key_ref nécessaire).
    r = admin_client.post(
        "/workspaces",
        headers=admin_headers,
        json={
            "name": "ws_smoke_ollama",
            "indexer": {
                "provider": "ollama",
                "model": "nomic-embed-text",
                "base_url": ollama_url,
            },
        },
    )
    assert r.status_code == 201, r.text
    api_key = r.json()["api_key"]

    # 2. Push un doc.
    r2 = admin_client.post(
        "/workspaces/ws_smoke_ollama/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "path": "smoke/hello.md",
            "content": "Hello vector world. This is a smoke test for push.",
        },
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["status"] == "indexed"
    assert body["chunks"] >= 1

    # 3. Vérifie pgvector : embeddings table contient au moins 1 ligne.
    import asyncio

    async def _check() -> int:
        admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
        admin = await asyncpg.connect(admin_dsn)
        try:
            row = await admin.fetchrow(
                "SELECT datname FROM pg_database WHERE datname = 'rag_ws_smoke_ollama'"
            )
            assert row is not None, "workspace DB missing"
        finally:
            await admin.close()

        ws_dsn = pg_container.rsplit("/", 1)[0] + "/rag_ws_smoke_ollama"
        conn = await asyncpg.connect(ws_dsn)
        try:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM embeddings WHERE path = $1",
                "smoke/hello.md",
            )
            return int(count or 0)
        finally:
            await conn.close()

    chunks_in_db = asyncio.get_event_loop().run_until_complete(_check())
    assert chunks_in_db >= 1
