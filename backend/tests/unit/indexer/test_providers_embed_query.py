from __future__ import annotations

import httpx
import pytest

from rag.indexer.providers.openai import OpenAIProvider
from rag.indexer.providers.protocol import EmbeddingProviderUnreachable


def _mock_transport(json_payload: dict) -> httpx.MockTransport:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=json_payload)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_openai_embed_query_returns_first_vector() -> None:
    transport = _mock_transport({"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]})
    provider = OpenAIProvider(
        model="text-embedding-3-small",
        api_key="sk-test",
        transport=transport,
    )
    vec = await provider.embed_query("hello")
    assert vec == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_openai_embed_query_raises_on_empty_response() -> None:
    transport = _mock_transport({"data": []})
    provider = OpenAIProvider(
        model="text-embedding-3-small",
        api_key="sk-test",
        transport=transport,
    )
    with pytest.raises(EmbeddingProviderUnreachable, match="empty embedding"):
        await provider.embed_query("hello")
