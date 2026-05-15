from __future__ import annotations

import asyncio

import asyncpg
import pytest
from fastapi.testclient import TestClient
from pgvector.asyncpg import register_vector


def _make_ws(client: TestClient, admin_headers: dict[str, str], name: str) -> str:
    r = client.post(
        "/workspaces",
        headers=admin_headers,
        json={
            "name": name,
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["api_key"]


class _FakeProvider:
    def __init__(self, vec: list[float]) -> None:
        self._vec = vec
        self.embed_query_calls = 0

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vec for _ in texts]

    async def embed_query(self, _text: str) -> list[float]:
        self.embed_query_calls += 1
        return self._vec


def _inject_fake_provider(vec: list[float]) -> _FakeProvider:
    """Patch services.mcp.make_provider so the router uses a fake."""
    fake = _FakeProvider(vec=vec)
    import rag.services.mcp as _mcp_mod

    _mcp_mod.make_provider = lambda **_kw: fake  # type: ignore[assignment]
    return fake


@pytest.fixture(autouse=True)
def _restore_make_provider():  # type: ignore[no-untyped-def]
    """Restore make_provider after each test to avoid leaking the monkey-patch."""
    import rag.services.mcp as _mcp_mod
    from rag.indexer.providers.factory import make_provider as _real

    yield
    _mcp_mod.make_provider = _real  # type: ignore[assignment]


async def _seed_embedding(
    pg_container: str,
    workspace_name: str,
    path: str,
    chunk_index: int,
    content: str,
    embedding: list[float],
) -> None:
    """Insert un row dans embeddings de la DB rag_<name>."""
    ws_dsn = pg_container.rsplit("/", 1)[0] + f"/rag_{workspace_name}"
    conn = await asyncpg.connect(ws_dsn)
    try:
        await register_vector(conn)
        await conn.execute(
            "INSERT INTO embeddings (path, chunk_index, content, embedding) "
            "VALUES ($1, $2, $3, $4)",
            path,
            chunk_index,
            content,
            embedding,
        )
    finally:
        await conn.close()


def test_mcp_single_returns_top_k_hits(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_mcp_a")

    # Vecteurs déterministes pour scores cosine prévisibles.
    # dim 1536 pour openai 3-small (cf. model_dimensions M2).
    # Tous les vecteurs sont normalisés (norme L2 = 1) pour que le score
    # cosine (= produit scalaire sur vecteurs unitaires) soit prévisible.
    dim = 1536
    near = [1.0] + [0.0] * (dim - 1)
    # mid : cosine avec near = 0.8 (angle ~37°), nettement > min_score=0.5
    mid = [0.8, 0.6] + [0.0] * (dim - 2)
    far = [0.0] * (dim - 1) + [1.0]

    async def _seed() -> None:
        await _seed_embedding(pg_container, "ws_mcp_a", "near.md", 0, "near content", near)
        await _seed_embedding(pg_container, "ws_mcp_a", "mid.md", 0, "mid content", mid)
        await _seed_embedding(pg_container, "ws_mcp_a", "far.md", 0, "far content", far)

    asyncio.get_event_loop().run_until_complete(_seed())

    _inject_fake_provider(vec=near)

    r = admin_client.post(
        "/mcp",
        json={
            "workspace": "ws_mcp_a",
            "api_key": api_key,
            "query": "test query",
            "top_k": 2,
            "min_score": 0.5,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["query"] == "test query"
    paths = [h["path"] for h in body["results"]]
    assert "near.md" in paths
    assert "mid.md" in paths
    # far.md cosine score proche de 0 → filtré par min_score=0.5
    assert "far.md" not in paths
    assert all(h["workspace"] == "ws_mcp_a" for h in body["results"])
    assert all(h["indexer"] == "openai/text-embedding-3-small" for h in body["results"])


def test_mcp_single_min_score_strict_returns_empty(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_mcp_strict")

    dim = 1536
    far = [0.0] * (dim - 1) + [1.0]
    near = [1.0] + [0.0] * (dim - 1)

    async def _seed() -> None:
        await _seed_embedding(pg_container, "ws_mcp_strict", "far.md", 0, "x", far)

    asyncio.get_event_loop().run_until_complete(_seed())

    _inject_fake_provider(vec=near)

    r = admin_client.post(
        "/mcp",
        json={
            "workspace": "ws_mcp_strict",
            "api_key": api_key,
            "query": "x",
            "min_score": 0.99,
        },
    )
    assert r.status_code == 200
    assert r.json()["results"] == []


def test_mcp_single_default_top_k_is_5(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_mcp_def")

    dim = 1536
    near = [1.0] + [0.0] * (dim - 1)

    async def _seed() -> None:
        for i in range(10):
            await _seed_embedding(
                pg_container,
                "ws_mcp_def",
                f"p{i}.md",
                0,
                "x",
                near,
            )

    asyncio.get_event_loop().run_until_complete(_seed())

    _inject_fake_provider(vec=near)

    r = admin_client.post(
        "/mcp",
        json={
            "workspace": "ws_mcp_def",
            "api_key": api_key,
            "query": "x",
            "min_score": 0.0,
        },
    )
    assert r.status_code == 200
    assert len(r.json()["results"]) == 5  # top_k default
