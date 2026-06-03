from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from rag.indexer.providers.protocol import (
    EmbeddingAuthError,
    EmbeddingProviderUnreachable,
    EmbeddingRateLimited,
)

log = structlog.get_logger(__name__)

_URL_INTERNATIONAL = (
    "https://dashscope-intl.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
)
_BATCH_SIZE = 25  # limite DashScope : 25 textes par requête pour text-embedding-v3/v4
_TIMEOUT = 30.0
_DEFAULT_RETRY_SLEEP = 2.0


class DashScopeEmbeddingProvider:
    """Provider embedding Alibaba DashScope (text-embedding-v3, text-embedding-v4).

    Format natif DashScope — body : input.texts.
    Réponse : output.embeddings[].{text_index, embedding}.
    `base_url` configurable pour switcher région (défaut : international).
    Batch max : 25 textes par requête.
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_sleep_seconds: float = _DEFAULT_RETRY_SLEEP,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._url = base_url or _URL_INTERNATIONAL
        self._transport = transport
        self._retry_sleep = retry_sleep_seconds

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self._api_key:
            raise EmbeddingAuthError("DashScope api_key is required (got None)")
        if not texts:
            return []

        results: list[list[float]] = []
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=_TIMEOUT,
        ) as client:
            for batch_start in range(0, len(texts), _BATCH_SIZE):
                batch = texts[batch_start : batch_start + _BATCH_SIZE]
                results.extend(await self._embed_batch(client, batch))
        return results

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        if not vectors:
            raise EmbeddingProviderUnreachable("DashScope returned empty embedding")
        return vectors[0]

    async def _embed_batch(
        self,
        client: httpx.AsyncClient,
        batch: list[str],
    ) -> list[list[float]]:
        body: dict[str, Any] = {
            "model": self._model,
            "input": {"texts": batch},
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        for attempt in (0, 1):
            try:
                response = await client.post(self._url, json=body, headers=headers)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt == 0:
                    log.warning("dashscope.embed.network_retry", error=str(e))
                    await asyncio.sleep(self._retry_sleep)
                    continue
                raise EmbeddingProviderUnreachable(
                    f"DashScope unreachable: {type(e).__name__}: {e}"
                ) from e

            if response.status_code == 200:
                return self._parse_response(response.json())

            if response.status_code in (401, 403):
                raise EmbeddingAuthError(f"DashScope auth error: HTTP {response.status_code}")

            if response.status_code in (429, 503):
                if attempt == 0:
                    log.warning("dashscope.embed.transient_retry", status=response.status_code)
                    await asyncio.sleep(self._retry_sleep)
                    continue
                if response.status_code == 429:
                    raise EmbeddingRateLimited("DashScope rate limit (after retry)")
                raise EmbeddingProviderUnreachable("DashScope 503 (after retry)")

            raise EmbeddingProviderUnreachable(
                f"DashScope unexpected status: HTTP {response.status_code}"
            )

        raise EmbeddingProviderUnreachable("DashScope: retry loop exited unexpectedly")

    @staticmethod
    def _parse_response(payload: dict[str, Any]) -> list[list[float]]:
        items = payload.get("output", {}).get("embeddings", [])
        return [
            item["embedding"]
            for item in sorted(items, key=lambda x: x.get("text_index", 0))
        ]
