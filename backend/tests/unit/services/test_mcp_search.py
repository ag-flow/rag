from __future__ import annotations

# Tests unitaires pour search() après T7.
# _authenticate fait un seul fetchrow (fingerprint JOIN) puis fetchval sur miss.
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from rag.api.errors import WorkspaceNotFound
from rag.auth.workspace_auth import ApiKeyCache
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
    def __init__(self, value: str = "resolved-secret") -> None:
        self.calls = 0
        self._value = value

    async def resolve_with_retry(self, _ref: str) -> str:
        self.calls += 1
        return self._value


class _MapResolver:
    """Resolver qui dispatche par ref (sous-chaîne du path)."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = mapping

    async def resolve_with_retry(self, ref: str) -> str:
        for key, val in self._mapping.items():
            if key in ref:
                return val
        raise KeyError(f"no mapping for {ref}")


def _ctx_row(name: str, provider: str, model: str, api_key_ref: str | None) -> dict[str, Any]:
    """Construit la row renvoyée par _load_workspace_context (fetchrow #2)."""
    return {
        "workspace_name": name,
        "rag_cnx": "dsn",
        "provider": provider,
        "model": model,
        "api_key_ref": api_key_ref,
        "base_url": None,
        "service": "openai",
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
    """Pool qui répond aux fetchrow de _authenticate + _load_workspace_context.

    _authenticate : fetchrow(fingerprint JOIN) → retourne row avec id+api_key_ref+indexer_used.
    _load_workspace_context : fetchrow(workspace context) → retourne ctx_row.
    fetchval : jamais appelé si fingerprint matche.
    """
    api_key_ref_val = api_key_ref or f"${{vault://rag:{name}_apikey}}"
    auth_row = {
        "id": ws_id,
        "api_key_ref": api_key_ref_val,
        "indexer_used": f"{provider}/{model}",
    }
    ctx_row = _ctx_row(name, provider, model, api_key_ref)

    call_count = 0

    async def _fetchrow(_query: str, *args: Any) -> dict[str, Any] | None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # _authenticate fingerprint lookup
            return auth_row
        if call_count == 2:
            # _load_workspace_context
            return ctx_row
        # _load_hybrid_config et appels ultérieurs → pas de config hybride
        return None

    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=_fetchrow)
    pool.fetchval = AsyncMock(return_value=None)  # jamais appelé sur happy path
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
    resolver = _FakeResolver(value=api_key)

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
    hits = await search(
        refs=[McpWorkspaceRef(name="ws_a", api_key=api_key)],
        query="hello",
        top_k=5,
        min_score=0.7,
        config_pool=pool,
        pool_registry=registry,
        apikey_cache=cache,
        secret_resolver=resolver,
        default_vault_name="rag",
        provider_factory=lambda **_kw: provider,  # type: ignore[arg-type]
    )

    assert len(hits) == 1
    assert hits[0].workspace == "ws_a"
    assert provider.calls == 1
    assert resolver.calls >= 1  # resolver appelé : auth workspace + indexer api_key_ref


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
    resolver = _FakeResolver(value=api_key)
    await search(
        refs=[McpWorkspaceRef(name="ws_ollama", api_key=api_key)],
        query="x",
        top_k=5,
        min_score=0.7,
        config_pool=pool,
        pool_registry=registry,
        apikey_cache=cache,
        secret_resolver=resolver,
        default_vault_name="rag",
        provider_factory=lambda **_kw: provider,  # type: ignore[arg-type]
    )
    # api_key_ref None dans ctx → pas de résolution Harpocrate pour l'indexeur,
    # mais il y en a une pour l'auth workspace (api_key_ref non None dans auth_row).
    # Le resolver est appelé 1 fois pour l'auth.
    assert resolver.calls == 1


@pytest.mark.asyncio
async def test_search_multi_workspace_concat_in_order(monkeypatch) -> None:
    """Deux workspaces : les hits sont concaténés (ordre non garanti via gather)."""
    ws_id_a = uuid4()
    ws_id_b = uuid4()

    # Pool unique qui dispatche par ws_name via les args
    ws_id_map = {"ws_a": ws_id_a, "ws_b": ws_id_b}
    n_map: dict[str, int] = {"ws_a": 0, "ws_b": 0}

    async def _fetchrow(_query: str, *args: Any) -> dict[str, Any] | None:
        # Détermine le workspace via l'arg ws_name (premier arg string dans les queries)
        ws_name: str | None = None
        for a in args:
            if isinstance(a, str) and a in ("ws_a", "ws_b"):
                ws_name = a
                break
        if ws_name is None:
            return None

        n_map[ws_name] += 1
        ws_id = ws_id_map[ws_name]
        provider = "openai" if ws_name == "ws_a" else "voyage"
        ref = f"${{vault://rag:{ws_name}_apikey}}"

        if n_map[ws_name] == 1:
            return {"id": ws_id, "api_key_ref": ref, "indexer_used": f"{provider}/m"}
        return _ctx_row(ws_name, provider, "m", None)

    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=_fetchrow)
    pool.fetchval = AsyncMock(return_value=None)

    ws_pool = MagicMock()
    registry = _fake_registry_returning(ws_pool)
    provider_stub = _FakeProvider(vec=[0.1])

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
    # Resolver retourne la bonne api_key par workspace ref
    resolver = _MapResolver({"ws_a_apikey": "k1", "ws_b_apikey": "k2"})
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
        secret_resolver=resolver,  # type: ignore[arg-type]
        default_vault_name="rag",
        provider_factory=lambda **_kw: provider_stub,  # type: ignore[arg-type]
    )

    assert set(h.workspace for h in hits) == {"ws_a", "ws_b"}


@pytest.mark.asyncio
async def test_search_fail_fast_on_workspace_not_found() -> None:
    cache = ApiKeyCache()
    pool = MagicMock()
    # fingerprint lookup → None, puis fetchval (exists) → None (workspace absent)
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetchval = AsyncMock(return_value=None)
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
            default_vault_name="rag",
        )


@pytest.mark.asyncio
async def test_search_fail_fast_on_bad_apikey() -> None:
    """Fingerprint ne matche pas (fetchrow None) + workspace existe → 401."""
    cache = ApiKeyCache()
    pool = MagicMock()
    # fetchrow → None (fingerprint lookup miss)
    pool.fetchrow = AsyncMock(return_value=None)
    # fetchval → 1 (workspace existe)
    pool.fetchval = AsyncMock(return_value=1)
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
            secret_resolver=_FakeResolver(),
            default_vault_name="rag",
        )
    assert exc.value.status_code == 401
