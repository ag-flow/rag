from __future__ import annotations

import json as _json

import httpx
import pytest

from rag.indexer.providers.openai import OpenAIProvider
from rag.indexer.providers.protocol import EmbeddingProviderUnreachable
from rag.indexer.providers.voyage import VoyageProvider


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


@pytest.mark.asyncio
async def test_voyage_embed_query_sends_input_type_query() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = _json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.5, 0.6]}]})

    transport = httpx.MockTransport(handler)
    provider = VoyageProvider(
        model="voyage-3-lite",
        api_key="vk-test",
        transport=transport,
    )
    vec = await provider.embed_query("ma question")

    assert vec == [0.5, 0.6]
    assert captured["body"]["input"] == ["ma question"]
    assert captured["body"]["input_type"] == "query"
    assert captured["body"]["model"] == "voyage-3-lite"


@pytest.mark.asyncio
async def test_voyage_embed_texts_still_uses_input_type_document() -> None:
    """Régression : embed_texts garde input_type=document."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = _json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})

    transport = httpx.MockTransport(handler)
    provider = VoyageProvider(
        model="voyage-3-lite",
        api_key="vk-test",
        transport=transport,
    )
    await provider.embed_texts(["du contenu"])
    assert captured["body"]["input_type"] == "document"
