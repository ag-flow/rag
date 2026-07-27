"""E2E tests : fallback dégradé MCP search quand le reranker est injoignable.

Vérifie que `RerankProviderError` (ici `RerankProviderUnreachable`) N'EST PAS
propagée jusqu'à l'appelant : `_search_one` retombe sur l'ordre vector/RRF non
reranké et la recherche reste disponible (BUG-002). Remplace l'ancien contrat
fail-fast du plan M8, invalidé par BUG-002.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import asyncpg
import pytest

from rag.db.pool import WorkspacePoolRegistry
from rag.rerank.protocol import RerankProvider, RerankProviderUnreachable
from rag.schemas.mcp import SearchHit
from rag.services.mcp import McpWorkspaceRef, search
from tests.integration._workspace_seed import seed_user_api_key, seed_workspace

# ---------------------------------------------------------------------------
# Constantes de test
# ---------------------------------------------------------------------------

_API_KEY = "e2e-failfast-test-key"
_WS_NAME = "ws_failfast_e2e"

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
]


class _StubResolver:
    """Retourne l'api_key réelle pour les refs workspace (compare_digest doit passer)."""

    async def resolve_with_retry(self, ref: str) -> str:
        return _API_KEY


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerank_provider_unreachable_falls_back_to_base_order(
    migrated: asyncpg.Pool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quand le reranker lève RerankProviderUnreachable, la recherche ne plante
    pas : elle retombe sur l'ordre vector/RRF non reranké (BUG-002)."""
    async with migrated.acquire() as conn:
        ws_id: UUID = await seed_workspace(
            conn,
            name=_WS_NAME,
            api_key=_API_KEY,
            rag_cnx="postgresql://unused/test",
            rag_base="rag_test",
        )
        await seed_user_api_key(conn, api_key=_API_KEY, scope="read_write")
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'ollama', 'mxbai-embed-large', 4)",
            ws_id,
        )
        # rerank_config présente (pas d'api_key_ref → pas de résolution Harpocrate)
        await conn.execute(
            "INSERT INTO rerank_configs "
            "(workspace_id, provider, model, base_url) "
            "VALUES ($1, 'ollama', 'bge', 'http://localhost:11434')",
            ws_id,
        )

    # Pool registry mock
    registry = MagicMock(spec=WorkspacePoolRegistry)
    registry.get_workspace_pool = AsyncMock(return_value=migrated)

    # vector_search retourne 2 hits → reranker sera appelé (> 1 hit)
    monkeypatch.setattr(
        "rag.services.mcp.vector_search",
        AsyncMock(return_value=list(_FAKE_HITS)),
    )

    # Embedding provider stub
    embed_stub = MagicMock()
    embed_stub.embed_query = AsyncMock(return_value=[0.1] * 4)

    def _embed_factory(**_kw: Any) -> Any:
        return embed_stub

    provider_factory: Any = _embed_factory

    # Reranker qui lève RerankProviderUnreachable
    failing_reranker = MagicMock(spec=RerankProvider)
    failing_reranker.rerank = AsyncMock(
        side_effect=RerankProviderUnreachable("cohere 503")
    )
    rerank_factory: Any = MagicMock(return_value=failing_reranker)

    hits, _channels = await search(
        refs=[McpWorkspaceRef(name=_WS_NAME, api_key=_API_KEY)],
        query="test query",
        top_k=2,
        min_score=0.0,
        config_pool=migrated,
        pool_registry=registry,
        secret_resolver=_StubResolver(),
        provider_factory=provider_factory,
        rerank_factory=rerank_factory,
    )

    # Vérifie que rerank() a bien été appelé (pas skippé)
    failing_reranker.rerank.assert_called_once()

    # Fallback : les hits sont renvoyés dans l'ordre vector/RRF d'origine.
    assert [h.path for h in hits] == ["doc_a.md", "doc_b.md"]
