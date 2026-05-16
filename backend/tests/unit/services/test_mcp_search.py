from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from rag.api.errors import WorkspaceNotFound
from rag.auth.workspace_auth import ApiKeyCache, _CacheEntry
from rag.schemas.mcp import SearchHit
from rag.services.mcp import McpWorkspaceRef, search


class _FakeProvider:
    def __init__(self, vec: list[float]) -> None:
        self._vec = vec
        self.calls = 0

    async def embed_query(self, _text: str) -> list[float]:
        self.calls += 1
        return self._vec

    async def embed_texts(self, _texts: list[str]) -> list[list[float]]:
        raise AssertionError("embed_texts not expected in search path")


class _FakeResolver:
    def __init__(self) -> None:
        self.calls = 0

    async def resolve_with_retry(self, _ref: str) -> str:
        self.calls += 1
        return "resolved-secret"


def _seeded_cache(name: str, api_key: str, workspace_id, indexer_used: str) -> ApiKeyCache:
    cache = ApiKeyCache(max_size=8, ttl_seconds=60)
    cache.put(
        name,
        api_key,
        _CacheEntry(
            workspace_id=workspace_id,
            indexer_used=indexer_used,
            inserted_at=time.monotonic(),
        ),
    )
    return cache


def _fake_pool_with_ctx(ctx_rows: dict[str, dict[str, Any]]) -> MagicMock:
    """pool.fetchrow renvoie le contexte par workspace name (param $1)."""

    async def _fetchrow(_query: str, name: str) -> dict[str, Any] | None:
        return ctx_rows.get(name)

    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=_fetchrow)
    return pool


def _fake_registry_returning(ws_pool: MagicMock) -> MagicMock:
    reg = MagicMock()
    reg.get_workspace_pool = AsyncMock(return_value=ws_pool)
    return reg


@pytest.mark.asyncio
async def test_search_single_workspace_returns_hits(monkeypatch) -> None:
    ws_id = uuid4()
    cache = _seeded_cache("ws_a", "k1", ws_id, "openai/text-embedding-3-small")
    pool = _fake_pool_with_ctx(
        {
            "ws_a": {
                "workspace_name": "ws_a",
                "rag_cnx": "dsn",
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_key",
                "base_url": None,
            },
        }
    )
    ws_pool = MagicMock()
    registry = _fake_registry_returning(ws_pool)
    provider = _FakeProvider(vec=[0.1, 0.2])

    fake_vector_search = AsyncMock(
        return_value=[
            SearchHit(
                workspace="ws_a",
                indexer="openai/text-embedding-3-small",
                path="a.md",
                chunk_index=0,
                content="x",
                score=0.9,
            ),
        ]
    )

    from rag.services import mcp

    monkeypatch.setattr(mcp, "vector_search", fake_vector_search)

    resolver = _FakeResolver()
    hits = await search(
        refs=[McpWorkspaceRef(name="ws_a", api_key="k1")],
        query="hello",
        top_k=5,
        min_score=0.7,
        config_pool=pool,
        pool_registry=registry,
        apikey_cache=cache,
        secret_resolver=resolver,
        provider_factory=lambda **_kw: provider,  # type: ignore[arg-type]
    )

    assert len(hits) == 1
    assert hits[0].workspace == "ws_a"
    assert provider.calls == 1
    assert resolver.calls == 1  # api_key_ref non-None → vault resolved


@pytest.mark.asyncio
async def test_search_skips_vault_when_api_key_ref_is_none(monkeypatch) -> None:
    ws_id = uuid4()
    cache = _seeded_cache("ws_ollama", "k1", ws_id, "ollama/nomic-embed-text")
    pool = _fake_pool_with_ctx(
        {
            "ws_ollama": {
                "workspace_name": "ws_ollama",
                "rag_cnx": "dsn",
                "provider": "ollama",
                "model": "nomic-embed-text",
                "api_key_ref": None,
                "base_url": "http://ollama:11434",
            },
        }
    )
    ws_pool = MagicMock()
    registry = _fake_registry_returning(ws_pool)
    provider = _FakeProvider(vec=[0.1])

    from rag.services import mcp

    monkeypatch.setattr(mcp, "vector_search", AsyncMock(return_value=[]))

    resolver = _FakeResolver()
    await search(
        refs=[McpWorkspaceRef(name="ws_ollama", api_key="k1")],
        query="x",
        top_k=5,
        min_score=0.7,
        config_pool=pool,
        pool_registry=registry,
        apikey_cache=cache,
        secret_resolver=resolver,
        provider_factory=lambda **_kw: provider,  # type: ignore[arg-type]
    )
    assert resolver.calls == 0  # api_key_ref None → no vault call


@pytest.mark.asyncio
async def test_search_multi_workspace_concat_in_order(monkeypatch) -> None:
    cache = ApiKeyCache(max_size=8, ttl_seconds=60)
    cache.put(
        "ws_a",
        "k1",
        _CacheEntry(
            workspace_id=uuid4(),
            indexer_used="openai/m",
            inserted_at=time.monotonic(),
        ),
    )
    cache.put(
        "ws_b",
        "k2",
        _CacheEntry(
            workspace_id=uuid4(),
            indexer_used="voyage/m",
            inserted_at=time.monotonic(),
        ),
    )

    pool = _fake_pool_with_ctx(
        {
            "ws_a": {
                "workspace_name": "ws_a",
                "rag_cnx": "dsn_a",
                "provider": "openai",
                "model": "m",
                "api_key_ref": None,
                "base_url": None,
            },
            "ws_b": {
                "workspace_name": "ws_b",
                "rag_cnx": "dsn_b",
                "provider": "voyage",
                "model": "m",
                "api_key_ref": None,
                "base_url": None,
            },
        }
    )
    ws_pool = MagicMock()
    registry = _fake_registry_returning(ws_pool)
    provider = _FakeProvider(vec=[0.1])

    async def _vector_search(_pool, **kw: Any) -> list[SearchHit]:
        name = kw["workspace_name"]
        return [
            SearchHit(
                workspace=name,
                indexer=kw["indexer_used"],
                path=f"{name}.md",
                chunk_index=0,
                content="x",
                score=0.9,
            )
        ]

    from rag.services import mcp

    monkeypatch.setattr(mcp, "vector_search", _vector_search)

    hits = await search(
        refs=[
            McpWorkspaceRef(name="ws_a", api_key="k1"),
            McpWorkspaceRef(name="ws_b", api_key="k2"),
        ],
        query="x",
        top_k=5,
        min_score=0.7,
        config_pool=pool,
        pool_registry=registry,
        apikey_cache=cache,
        secret_resolver=_FakeResolver(),
        provider_factory=lambda **_kw: provider,  # type: ignore[arg-type]
    )

    assert [h.workspace for h in hits] == ["ws_a", "ws_b"]


@pytest.mark.asyncio
async def test_search_fail_fast_on_workspace_not_found() -> None:
    cache = ApiKeyCache(max_size=8, ttl_seconds=60)
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)  # workspace inexistant
    registry = MagicMock()

    with pytest.raises(WorkspaceNotFound):
        await search(
            refs=[McpWorkspaceRef(name="ghost", api_key="k")],
            query="x",
            top_k=5,
            min_score=0.7,
            config_pool=pool,
            pool_registry=registry,
            apikey_cache=cache,
            secret_resolver=_FakeResolver(),
        )


@pytest.mark.asyncio
async def test_search_fail_fast_on_bad_apikey(monkeypatch) -> None:
    cache = ApiKeyCache(max_size=8, ttl_seconds=60)
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "id": uuid4(),
            "api_key_hash": "$2b$12$x",
            "indexer_used": "openai/m",
        }
    )
    registry = MagicMock()

    from rag.services import mcp

    monkeypatch.setattr(mcp, "verify_api_key", lambda _k, _h: False)

    with pytest.raises(HTTPException) as exc:
        await search(
            refs=[McpWorkspaceRef(name="ws", api_key="bad")],
            query="x",
            top_k=5,
            min_score=0.7,
            config_pool=pool,
            pool_registry=registry,
            apikey_cache=cache,
            secret_resolver=_FakeResolver(),
        )
    assert exc.value.status_code == 401
