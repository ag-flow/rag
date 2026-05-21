from __future__ import annotations

# Tests unitaires pour search() (T1 -- _authenticate lookup DB direct).
# NOTE(T6): _authenticate n'utilise plus le cache. Chaque appel search effectue
# 3 fetchrow par workspace : existence check, fingerprint lookup, load_context.
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from rag.api.errors import WorkspaceNotFound
from rag.auth.workspace_auth import ApiKeyCache
from rag.schemas.mcp import SearchHit
from rag.services.mcp import McpWorkspaceRef, search

_DEK = "x" * 32


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


def _ctx_row(name: str, provider: str, model: str, api_key_ref: str | None) -> dict[str, Any]:
    """Construit la row renvoyee par _load_workspace_context (fetchrow #3)."""
    return {
        "workspace_name": name,
        "rag_cnx": "dsn",
        "provider": provider,
        "model": model,
        "api_key_ref": api_key_ref,
        "base_url": None,
        "rerank_provider": None,
        "rerank_model": None,
        "rerank_api_key_ref": None,
        "rerank_base_url": None,
        "rerank_top_k_pre_rerank": None,
    }


def _pool_for_workspace(
    ws_id,
    api_key: str,
    name: str,
    provider: str,
    model: str,
    api_key_ref: str | None,
) -> MagicMock:
    """Pool qui repond aux 3 fetchrow de _authenticate + _load_workspace_context."""
    fingerprint_row = {"stored": api_key}
    ctx_row = _ctx_row(name, provider, model, api_key_ref)

    call_count = 0

    async def _fetchrow(_query: str, *args: Any) -> dict[str, Any] | None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # existence check
            return {"id": ws_id, "indexer_used": f"{provider}/{model}"}
        if call_count == 2:
            # fingerprint lookup
            return fingerprint_row
        # load_workspace_context
        return ctx_row

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
    api_key = "k1"
    pool = _pool_for_workspace(
        ws_id, api_key, "ws_a", "openai", "text-embedding-3-small", "openai_key"
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

    cache = ApiKeyCache()
    resolver = _FakeResolver()
    hits = await search(
        refs=[McpWorkspaceRef(name="ws_a", api_key=api_key)],
        query="hello",
        top_k=5,
        min_score=0.7,
        config_pool=pool,
        pool_registry=registry,
        apikey_cache=cache,
        api_key_dek=_DEK,
        secret_resolver=resolver,
        default_vault_name="rag",
        provider_factory=lambda **_kw: provider,  # type: ignore[arg-type]
    )

    assert len(hits) == 1
    assert hits[0].workspace == "ws_a"
    assert provider.calls == 1
    assert resolver.calls == 1  # api_key_ref non-None -> vault resolved


@pytest.mark.asyncio
async def test_search_skips_vault_when_api_key_ref_is_none(monkeypatch) -> None:
    ws_id = uuid4()
    api_key = "k1"
    pool = _pool_for_workspace(ws_id, api_key, "ws_ollama", "ollama", "nomic-embed-text", None)
    ws_pool = MagicMock()
    registry = _fake_registry_returning(ws_pool)
    provider = _FakeProvider(vec=[0.1])

    from rag.services import mcp

    monkeypatch.setattr(mcp, "vector_search", AsyncMock(return_value=[]))

    cache = ApiKeyCache()
    resolver = _FakeResolver()
    await search(
        refs=[McpWorkspaceRef(name="ws_ollama", api_key=api_key)],
        query="x",
        top_k=5,
        min_score=0.7,
        config_pool=pool,
        pool_registry=registry,
        apikey_cache=cache,
        api_key_dek=_DEK,
        secret_resolver=resolver,
        default_vault_name="rag",
        provider_factory=lambda **_kw: provider,  # type: ignore[arg-type]
    )
    assert resolver.calls == 0  # api_key_ref None -> no vault call


@pytest.mark.asyncio
async def test_search_multi_workspace_concat_in_order(monkeypatch) -> None:
    """Deux workspaces : les hits sont concatenes (ordre exact non garanti via gather)."""
    ws_id_a = uuid4()
    ws_id_b = uuid4()

    # _search_one appelle _authenticate (2 fetchrow) puis _load_workspace_context (1).
    # asyncio.gather lance les 2 taches en concurrence ; on identifie les calls
    # par le nom du workspace dans les args SQL quand c'est disponible.
    # - existence check : (sql, ws_name)           -> args[0] = ws_name
    # - fingerprint lookup : (sql, dek, ws_name, fp) -> args[1] = ws_name
    # - load context : (sql, ws_name)               -> args[0] = ws_name
    a_count: dict[str, int] = {"ws_a": 0, "ws_b": 0}

    async def _fetchrow(_query: str, *args: Any) -> dict[str, Any] | None:
        # Determine workspace name from args
        ws_name: str | None = None
        if len(args) == 1 and isinstance(args[0], str) and args[0] in ("ws_a", "ws_b"):
            ws_name = args[0]
        elif len(args) >= 2 and isinstance(args[1], str) and args[1] in ("ws_a", "ws_b"):
            ws_name = args[1]

        if ws_name is None:
            return None

        a_count[ws_name] += 1
        call_n = a_count[ws_name]
        ws_id = ws_id_a if ws_name == "ws_a" else ws_id_b
        provider = "openai" if ws_name == "ws_a" else "voyage"
        api_key = "k1" if ws_name == "ws_a" else "k2"

        if call_n == 1:  # existence check
            return {"id": ws_id, "indexer_used": f"{provider}/m"}
        if call_n == 2:  # fingerprint lookup
            return {"stored": api_key}
        # load context
        return _ctx_row(ws_name, provider, "m", None)

    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=_fetchrow)
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

    cache = ApiKeyCache()
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
        api_key_dek=_DEK,
        secret_resolver=_FakeResolver(),
        default_vault_name="rag",
        provider_factory=lambda **_kw: provider,  # type: ignore[arg-type]
    )

    assert set(h.workspace for h in hits) == {"ws_a", "ws_b"}


@pytest.mark.asyncio
async def test_search_fail_fast_on_workspace_not_found() -> None:
    cache = ApiKeyCache()
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
            api_key_dek=_DEK,
            secret_resolver=_FakeResolver(),
            default_vault_name="rag",
        )


@pytest.mark.asyncio
async def test_search_fail_fast_on_bad_apikey() -> None:
    """Cle invalide (fingerprint non trouve) -> 401."""
    cache = ApiKeyCache()
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        side_effect=[
            {"id": uuid4(), "indexer_used": "openai/m"},
            None,  # fingerprint lookup returns None (key not found)
        ]
    )
    registry = MagicMock()

    with pytest.raises(HTTPException) as exc:
        await search(
            refs=[McpWorkspaceRef(name="ws", api_key="bad")],
            query="x",
            top_k=5,
            min_score=0.7,
            config_pool=pool,
            pool_registry=registry,
            apikey_cache=cache,
            api_key_dek=_DEK,
            secret_resolver=_FakeResolver(),
            default_vault_name="rag",
        )
    assert exc.value.status_code == 401
