from __future__ import annotations

import json

import httpx
import pytest

from rag.indexer.providers.protocol import EmbeddingAuthError
from rag.indexer.providers.voyage import VoyageProvider


def _vec(dim: int = 1024, fill: float = 0.2) -> list[float]:
    return [fill] * dim


@pytest.mark.asyncio
async def test_voyage_embed_texts_success_uses_input_type_document() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        data = [{"embedding": _vec(), "index": i} for i in range(len(captured["body"]["input"]))]
        return httpx.Response(200, json={"data": data})

    provider = VoyageProvider(
        model="voyage-3",
        api_key="vk-test",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_texts(["hello", "world"])
    assert len(result) == 2
    assert len(result[0]) == 1024
    # Le body doit inclure input_type=document
    assert captured["body"]["input_type"] == "document"
    assert captured["body"]["model"] == "voyage-3"


@pytest.mark.asyncio
async def test_voyage_embed_texts_missing_api_key_raises() -> None:
    provider = VoyageProvider(model="voyage-3", api_key=None)
    with pytest.raises(EmbeddingAuthError):
        await provider.embed_texts(["hello"])
