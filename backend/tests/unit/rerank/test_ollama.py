from __future__ import annotations

import httpx
import pytest

from rag.rerank.protocol import (
    RerankAuthError,
    RerankProviderUnreachable,
    RerankRateLimited,
)
from rag.rerank.providers.ollama import OllamaRerankProvider


def _mock_transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_ollama_returns_sorted_indices() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/api/rerank" in str(request.url)
        return httpx.Response(200, json={
            "results": [
                {"index": 0, "relevance_score": 0.7},
                {"index": 2, "relevance_score": 0.5},
            ],
        })
    provider = OllamaRerankProvider(
        model="bge-reranker-v2-m3",
        base_url="http://localhost:11434",
        transport=_mock_transport(handler),
    )
    indices = await provider.rerank(query="q", documents=["a", "b", "c"], top_k=2)
    assert indices == [0, 2]


@pytest.mark.asyncio
async def test_ollama_auth_error_on_401() -> None:
    """Ollama n'a pas d'auth normalement, mais on traite 401/403 par symétrie."""
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(401)
    provider = OllamaRerankProvider(
        model="bge", base_url="http://localhost:11434",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankAuthError):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_ollama_rate_limited_on_429() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(429)
    provider = OllamaRerankProvider(
        model="bge", base_url="http://localhost:11434",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankRateLimited):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_ollama_unreachable_on_5xx() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(500)
    provider = OllamaRerankProvider(
        model="bge", base_url="http://localhost:11434",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_ollama_unreachable_on_timeout() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")
    provider = OllamaRerankProvider(
        model="bge", base_url="http://localhost:11434",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)
