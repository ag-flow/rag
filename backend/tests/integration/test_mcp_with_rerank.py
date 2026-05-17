"""E2E tests : service MCP search avec reranking activé / désactivé / singleton.

Stratégie :
- `migrated` fixture (conftest integration) : base fraîche avec toutes les migrations.
- `seed_workspace` + INSERT indexer_configs + INSERT rerank_configs.
- monkeypatch de `rag.services.mcp.vector_search` pour retourner des SearchHit
  prédéfinis, sans avoir besoin d'une base pgvector peuplée.
- `provider_factory` et `rerank_factory` injectés directement via kwargs de `search()`.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import asyncpg
import pytest

from rag.auth.workspace_auth import ApiKeyCache
from rag.db.pool import WorkspacePoolRegistry
from rag.rerank.protocol import RerankProvider
from rag.schemas.mcp import SearchHit
from rag.services.mcp import McpWorkspaceRef, search
from tests.integration._workspace_seed import seed_workspace

# ---------------------------------------------------------------------------
# Constantes de test
# ---------------------------------------------------------------------------

_DEK = "x" * 32
_API_KEY = "e2e-rerank-test-key"
_WS_NAME = "ws_rerank_e2e"

# 3 hits prédéfinis — utilisés comme résultat de vector_search mocké
_FAKE_HITS = [
    SearchHit(
        workspace=_WS_NAME,
        indexer="ollama/mxbai-embed-large",
        path="doc_a.md",
        chunk_index=0,
        content="Content A",
        score=0.9,
    ),
    SearchHit(
        workspace=_WS_NAME,
        indexer="ollama/mxbai-embed-large",
        path="doc_b.md",
        chunk_index=0,
        content="Content B",
        score=0.8,
    ),
    SearchHit(
        workspace=_WS_NAME,
        indexer="ollama/mxbai-embed-large",
        path="doc_c.md",
        chunk_index=0,
        content="Content C",
        score=0.7,
    ),
]

# ---------------------------------------------------------------------------
# Helpers stubs
# ---------------------------------------------------------------------------


def _make_embedding_provider_factory() -> Callable[..., Any]:
    """Factory qui retourne un stub EmbeddingProvider avec embed_query fixe."""
    stub = MagicMock()
    stub.embed_query = AsyncMock(return_value=[0.1] * 4)
    return lambda **_: stub


def _make_rerank_factory(indices: list[int]) -> tuple[Callable[..., Any], MagicMock]:
    """Retourne (factory, stub_reranker) — stub_reranker.rerank() retourne `indices`."""
    stub = MagicMock(spec=RerankProvider)
    stub.rerank = AsyncMock(return_value=indices)
    factory = MagicMock(return_value=stub)
    return factory, stub


def _make_non_called_rerank_factory() -> tuple[Callable[..., Any], MagicMock]:
    """Retourne (factory, stub) ; factory ne doit PAS être appelée."""
    factory = MagicMock()
    return factory, factory


class _StubResolver:
    async def resolve_with_retry(self, ref: str) -> str:
        return "stubbed"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def ws_with_rerank(migrated: asyncpg.Pool) -> tuple[asyncpg.Pool, UUID, WorkspacePoolRegistry]:
    """Seed un workspace avec indexer_config + rerank_config (ollama/bge)."""
    async with migrated.acquire() as conn:
        ws_id = await seed_workspace(
            conn,
            name=_WS_NAME,
            api_key=_API_KEY,
            dek=_DEK,
            rag_cnx="postgresql://unused/test",
            rag_base="rag_test",
        )
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'ollama', 'mxbai-embed-large', 4)",
            ws_id,
        )
        # pas d'api_key_ref → pas de résolution Harpocrate
        await conn.execute(
            "INSERT INTO rerank_configs "
            "(workspace_id, provider, model, base_url) "
            "VALUES ($1, 'ollama', 'bge', 'http://localhost:11434')",
            ws_id,
        )

    registry = MagicMock(spec=WorkspacePoolRegistry)
    # get_workspace_pool retourne la même pool migrated (pas utilisée car vector_search est mocké)
    registry.get_workspace_pool = AsyncMock(return_value=migrated)

    return migrated, ws_id, registry


@pytest.fixture
async def ws_without_rerank(migrated: asyncpg.Pool) -> tuple[asyncpg.Pool, UUID, WorkspacePoolRegistry]:
    """Seed un workspace avec indexer_config mais sans rerank_config."""
    async with migrated.acquire() as conn:
        ws_id = await seed_workspace(
            conn,
            name=_WS_NAME,
            api_key=_API_KEY,
            dek=_DEK,
            rag_cnx="postgresql://unused/test",
            rag_base="rag_test",
        )
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'ollama', 'mxbai-embed-large', 4)",
            ws_id,
        )
    registry = MagicMock(spec=WorkspacePoolRegistry)
    registry.get_workspace_pool = AsyncMock(return_value=migrated)
    return migrated, ws_id, registry


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerank_changes_order_when_configured(
    ws_with_rerank: tuple[asyncpg.Pool, UUID, WorkspacePoolRegistry],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quand rerank_config est présente, l'ordre des hits suit les indices retournés
    par le reranker — ici [2, 0, 1] → Content C, Content A, Content B."""
    config_pool, _ws_id, registry = ws_with_rerank

    monkeypatch.setattr(
        "rag.services.mcp.vector_search",
        AsyncMock(return_value=list(_FAKE_HITS)),
    )

    # reranker retourne [2, 0, 1] → doc_c, doc_a, doc_b
    rerank_factory, stub_reranker = _make_rerank_factory([2, 0, 1])

    hits = await search(
        refs=[McpWorkspaceRef(name=_WS_NAME, api_key=_API_KEY)],
        query="test query",
        top_k=3,
        min_score=0.0,
        config_pool=config_pool,
        pool_registry=registry,
        apikey_cache=ApiKeyCache(),
        api_key_dek=_DEK,
        secret_resolver=_StubResolver(),
        provider_factory=_make_embedding_provider_factory(),
        rerank_factory=rerank_factory,
    )

    assert len(hits) == 3
    assert hits[0].path == "doc_c.md", f"expected doc_c.md first, got {hits[0].path}"
    assert hits[1].path == "doc_a.md", f"expected doc_a.md second, got {hits[1].path}"
    assert hits[2].path == "doc_b.md", f"expected doc_b.md third, got {hits[2].path}"
    stub_reranker.rerank.assert_called_once()


@pytest.mark.asyncio
async def test_no_rerank_when_not_configured(
    ws_without_rerank: tuple[asyncpg.Pool, UUID, WorkspacePoolRegistry],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sans rerank_config, l'ordre pgvector est préservé et le rerank_factory
    n'est pas invoqué."""
    config_pool, _ws_id, registry = ws_without_rerank

    monkeypatch.setattr(
        "rag.services.mcp.vector_search",
        AsyncMock(return_value=list(_FAKE_HITS)),
    )

    rerank_factory, _ = _make_non_called_rerank_factory()

    hits = await search(
        refs=[McpWorkspaceRef(name=_WS_NAME, api_key=_API_KEY)],
        query="test query",
        top_k=3,
        min_score=0.0,
        config_pool=config_pool,
        pool_registry=registry,
        apikey_cache=ApiKeyCache(),
        api_key_dek=_DEK,
        secret_resolver=_StubResolver(),
        provider_factory=_make_embedding_provider_factory(),
        rerank_factory=rerank_factory,
    )

    # Ordre pgvector préservé (doc_a, doc_b, doc_c)
    assert len(hits) == 3
    assert hits[0].path == "doc_a.md"
    assert hits[1].path == "doc_b.md"
    assert hits[2].path == "doc_c.md"
    # factory jamais appelée (pas de rerank_config → reranker jamais instancié)
    rerank_factory.assert_not_called()


@pytest.mark.asyncio
async def test_rerank_skipped_for_singleton(
    ws_with_rerank: tuple[asyncpg.Pool, UUID, WorkspacePoolRegistry],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quand vector_search retourne 1 seul hit, le reranker ne doit pas être
    appelé (singleton skip — reranker n'apporte rien avec 1 document)."""
    config_pool, _ws_id, registry = ws_with_rerank

    single_hit = [_FAKE_HITS[0]]
    monkeypatch.setattr(
        "rag.services.mcp.vector_search",
        AsyncMock(return_value=single_hit),
    )

    rerank_factory, stub_reranker = _make_rerank_factory([0])

    hits = await search(
        refs=[McpWorkspaceRef(name=_WS_NAME, api_key=_API_KEY)],
        query="test query",
        top_k=3,
        min_score=0.0,
        config_pool=config_pool,
        pool_registry=registry,
        apikey_cache=ApiKeyCache(),
        api_key_dek=_DEK,
        secret_resolver=_StubResolver(),
        provider_factory=_make_embedding_provider_factory(),
        rerank_factory=rerank_factory,
    )

    assert len(hits) == 1
    assert hits[0].path == "doc_a.md"
    # factory jamais appelée — le bloc rerank est entièrement skippé (singleton)
    rerank_factory.assert_not_called()
    stub_reranker.rerank.assert_not_called()
