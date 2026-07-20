from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import seed_endpoint_sync

pytestmark = pytest.mark.smoke


@pytest.fixture
def ollama_url() -> str:
    url = os.environ.get("OLLAMA_TEST_URL")
    if not url:
        pytest.skip("OLLAMA_TEST_URL non défini — smoke /mcp Ollama sauté.")
    return url


def test_mcp_e2e_ollama_search_returns_relevant_doc(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    ollama_url: str,
) -> None:
    """End-to-end : crée workspace Ollama, push 2 docs sémantiquement
    distincts, /mcp avec une query proche du doc A doit retourner doc A
    en tête."""
    # 1. Crée workspace Ollama (pas d'api_key_ref pour Ollama).
    # Utilise mxbai-embed-large (disponible homelab, 1024 dim).
    r = admin_client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={
            "name": "ws_mcp_smoke",
            "label": "ws_mcp_smoke",
            "endpoint_id": seed_endpoint_sync(
                os.environ["DATABASE_URL"],
                slug="ep-ws_mcp_smoke", provider="ollama",
                model="mxbai-embed-large", api_key_ref=None, base_url=ollama_url,
            ),
        },
    )
    assert r.status_code == 201, r.text
    kr = admin_client.post(
        "/api/me/api-keys",
        headers=admin_headers,
        json={"name": "key-smoke", "scope": "read_write"},
    )
    assert kr.status_code == 201, kr.text
    api_key = kr.json()["api_key"]
    push_headers = {"Authorization": f"Bearer {api_key}"}

    # 2. Push 2 documents distincts.
    r1 = admin_client.post(
        "/workspaces/ws_mcp_smoke/index",
        headers=push_headers,
        json={
            "path": "topic/docker.md",
            "content": "Docker provides containerization through Linux namespaces and cgroups.",
        },
    )
    assert r1.status_code == 200, r1.text

    r2 = admin_client.post(
        "/workspaces/ws_mcp_smoke/index",
        headers=push_headers,
        json={
            "path": "topic/cooking.md",
            "content": "To make a perfect omelette, beat the eggs with cream and salt.",
        },
    )
    assert r2.status_code == 200, r2.text

    # 3. Query proche du sujet Docker.
    r3 = admin_client.post(
        "/api/v1/search",
        json={
            "workspace": "ws_mcp_smoke",
            "api_key": api_key,
            "query": "How do Linux containers work?",
            "top_k": 5,
            "min_score": 0.0,
        },
    )
    assert r3.status_code == 200, r3.text
    body = r3.json()
    assert len(body["results"]) >= 1
    top_path = body["results"][0]["path"]
    assert top_path == "topic/docker.md", f"expected docker.md on top, got {top_path}"
    assert body["results"][0]["score"] > 0.3
