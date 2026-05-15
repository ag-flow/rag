from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.db.workspace_search import vector_search


def _make_pool_returning(rows: list[dict]) -> MagicMock:
    """Fake asyncpg.Pool avec acquire()→connection qui retourne `rows`."""
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)
    conn.execute = AsyncMock(return_value="SET")  # SET ivfflat.probes = 10
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


@pytest.mark.asyncio
async def test_vector_search_overfetches_4x_top_k(monkeypatch) -> None:
    """vector_search doit demander LIMIT $2 = top_k * 4 à pgvector."""
    from rag.db import workspace_search

    monkeypatch.setattr(workspace_search, "register_vector", AsyncMock())

    rows: list[dict] = []
    pool = _make_pool_returning(rows)

    await vector_search(
        pool,
        query_vec=[0.1, 0.2],
        top_k=5,
        min_score=0.0,
        workspace_name="ws",
        indexer_used="openai/m",
    )

    conn = pool.acquire.return_value.__aenter__.return_value
    # 2e arg de conn.fetch = LIMIT
    args = conn.fetch.call_args[0]
    assert args[2] == 5 * 4  # over-fetch


@pytest.mark.asyncio
async def test_vector_search_filters_below_min_score(monkeypatch) -> None:
    from rag.db import workspace_search

    monkeypatch.setattr(workspace_search, "register_vector", AsyncMock())

    rows = [
        {"path": "a.md", "chunk_index": 0, "content": "hi", "score": 0.95},
        {"path": "b.md", "chunk_index": 0, "content": "lo", "score": 0.50},
        {"path": "c.md", "chunk_index": 0, "content": "mid", "score": 0.80},
    ]
    pool = _make_pool_returning(rows)

    hits = await vector_search(
        pool,
        query_vec=[0.1],
        top_k=10,
        min_score=0.7,
        workspace_name="ws",
        indexer_used="openai/m",
    )
    assert [h.path for h in hits] == ["a.md", "c.md"]
    assert all(h.score >= 0.7 for h in hits)


@pytest.mark.asyncio
async def test_vector_search_slices_to_top_k_after_filter(monkeypatch) -> None:
    from rag.db import workspace_search

    monkeypatch.setattr(workspace_search, "register_vector", AsyncMock())

    rows = [
        {"path": f"p{i}.md", "chunk_index": 0, "content": "x", "score": 0.9 - i * 0.01}
        for i in range(10)
    ]
    pool = _make_pool_returning(rows)

    hits = await vector_search(
        pool,
        query_vec=[0.1],
        top_k=3,
        min_score=0.0,
        workspace_name="ws",
        indexer_used="openai/m",
    )
    assert len(hits) == 3
    assert [h.path for h in hits] == ["p0.md", "p1.md", "p2.md"]


@pytest.mark.asyncio
async def test_vector_search_returns_search_hit_with_workspace_and_indexer(monkeypatch) -> None:
    from rag.db import workspace_search

    monkeypatch.setattr(workspace_search, "register_vector", AsyncMock())

    rows = [{"path": "x.md", "chunk_index": 7, "content": "blob", "score": 0.88}]
    pool = _make_pool_returning(rows)

    hits = await vector_search(
        pool,
        query_vec=[0.1],
        top_k=5,
        min_score=0.0,
        workspace_name="ws_test",
        indexer_used="voyage/voyage-3-lite",
    )
    assert len(hits) == 1
    h = hits[0]
    assert h.workspace == "ws_test"
    assert h.indexer == "voyage/voyage-3-lite"
    assert h.path == "x.md"
    assert h.chunk_index == 7
    assert h.content == "blob"
    assert h.score == 0.88


@pytest.mark.asyncio
async def test_vector_search_empty_rows_returns_empty(monkeypatch) -> None:
    from rag.db import workspace_search

    monkeypatch.setattr(workspace_search, "register_vector", AsyncMock())

    pool = _make_pool_returning([])
    hits = await vector_search(
        pool,
        query_vec=[0.1],
        top_k=5,
        min_score=0.0,
        workspace_name="ws",
        indexer_used="openai/m",
    )
    assert hits == []
