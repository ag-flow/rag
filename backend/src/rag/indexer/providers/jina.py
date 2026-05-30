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

_JINA_URL = "https://api.jina.ai/v1/embeddings"
_BATCH_SIZE = 100
_TIMEOUT_SECONDS = 30.0
_DEFAULT_RETRY_SLEEP_SECONDS = 2.0


class JinaProvider:
    """Provider embedding Jina AI.

    Endpoint : POST https://api.jina.ai/v1/embeddings
    Supporte le parametre `task` : "retrieval.passage" pour l'indexation,
    "retrieval.query" pour les requetes de recherche.
    Modeles : jina-embeddings-v3 (1024 dim, MRL, 8192 tokens ctx).
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_sleep_seconds: float = _DEFAULT_RETRY_SLEEP_SECONDS,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._transport = transport
        self._retry_sleep = retry_sleep_seconds

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self._api_key:
            raise EmbeddingAuthError("Jina api_key is required (got None)")
        if not texts:
            return []
        results: list[list[float]] = []
        async with httpx.AsyncClient(
            transport=self._transport, timeout=_TIMEOUT_SECONDS
        ) as client:
            for i in range(0, len(texts), _BATCH_SIZE):
                batch = texts[i : i + _BATCH_SIZE]
                results.extend(
                    await self._embed_batch(client, batch, task="retrieval.passage")
                )
        return results

    async def embed_query(self, text: str) -> list[float]:
        if not self._api_key:
            raise EmbeddingAuthError("Jina api_key is required (got None)")
        async with httpx.AsyncClient(
            transport=self._transport, timeout=_TIMEOUT_SECONDS
        ) as client:
            result = await self._embed_batch(client, [text], task="retrieval.query")
        if not result:
            raise EmbeddingProviderUnreachable("Jina returned empty embedding")
        return result[0]

    async def _embed_batch(
        self, client: httpx.AsyncClient, batch: list[str], *, task: str
    ) -> list[list[float]]:
        for attempt in (0, 1):
            try:
                response = await client.post(
                    _JINA_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": self._model, "input": batch, "task": task},
                )
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt == 0:
                    log.warning("jina.embed.network_retry", error=str(e))
                    await asyncio.sleep(self._retry_sleep)
                    continue
                raise EmbeddingProviderUnreachable(
                    f"Jina unreachable: {type(e).__name__}: {e}"
                ) from e

            if response.status_code == 200:
                return self._parse_response(response.json())
            if response.status_code in (401, 403):
                raise EmbeddingAuthError(
                    f"Jina auth error: HTTP {response.status_code}"
                )
            if response.status_code in (429, 503):
                if attempt == 0:
                    log.warning(
                        "jina.embed.transient_retry", status=response.status_code
                    )
                    await asyncio.sleep(self._retry_sleep)
                    continue
                if response.status_code == 429:
                    raise EmbeddingRateLimited("Jina rate limit (after retry)")
                raise EmbeddingProviderUnreachable("Jina 503 (after retry)")
            raise EmbeddingProviderUnreachable(
                f"Jina unexpected status: HTTP {response.status_code}"
            )
        raise EmbeddingProviderUnreachable("Jina: retry loop exited unexpectedly")

    @staticmethod
    def _parse_response(payload: dict[str, Any]) -> list[list[float]]:
        items = payload.get("data", [])
        return [item["embedding"] for item in sorted(items, key=lambda x: x.get("index", 0))]
