from __future__ import annotations

import httpx
import pytest

from rag.rerank.protocol import (
    RerankAuthError,
    RerankProviderUnreachable,
    RerankRateLimited,
)
from rag.rerank.providers.azure_foundry import AzureFoundryRerankProvider

_ENDPOINT = "https://proj.services.ai.azure.com/providers/cohere/v2/rerank"


def _mock_transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_azure_foundry_uses_base_url_verbatim_and_bearer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # base_url est utilisé tel quel comme URL complète (aucun path ajouté).
        assert str(request.url) == _ENDPOINT
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json={
            "results": [
                {"index": 2, "relevance_score": 0.99},
                {"index": 0, "relevance_score": 0.50},
                {"index": 1, "relevance_score": 0.10},
            ],
        })
    provider = AzureFoundryRerankProvider(
        model="rerank-v3.5", api_key="test-key", base_url=_ENDPOINT,
        transport=_mock_transport(handler),
    )
    results = await provider.rerank(query="q", documents=["a", "b", "c"], top_k=3)
    assert results == [(2, 0.99), (0, 0.50), (1, 0.10)]


@pytest.mark.asyncio
async def test_azure_foundry_empty_documents_short_circuits() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise AssertionError("no HTTP call expected for empty documents")
    provider = AzureFoundryRerankProvider(
        model="rerank-v3.5", api_key="k", base_url=_ENDPOINT,
        transport=_mock_transport(handler),
    )
    assert await provider.rerank(query="q", documents=[], top_k=3) == []


@pytest.mark.asyncio
async def test_azure_foundry_auth_error_on_401() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "invalid key"})
    provider = AzureFoundryRerankProvider(
        model="rerank-v3.5", api_key="bad", base_url=_ENDPOINT,
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankAuthError):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_azure_foundry_rate_limited_on_429() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(429)
    provider = AzureFoundryRerankProvider(
        model="rerank-v3.5", api_key="k", base_url=_ENDPOINT,
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankRateLimited):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_azure_foundry_unreachable_on_5xx() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(503)
    provider = AzureFoundryRerankProvider(
        model="rerank-v3.5", api_key="k", base_url=_ENDPOINT,
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_azure_foundry_unreachable_on_timeout() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout")
    provider = AzureFoundryRerankProvider(
        model="rerank-v3.5", api_key="k", base_url=_ENDPOINT,
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)
