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

_VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
_BATCH_SIZE = 128
_TIMEOUT_SECONDS = 30.0
_DEFAULT_RETRY_SLEEP_SECONDS = 2.0


class VoyageProvider:
    """Implementation `EmbeddingProvider` pour Voyage AI.

    Endpoint : `POST https://api.voyageai.com/v1/embeddings`.
    Batch jusqu'a 128 textes (limite Voyage), avec `input_type="document"`
    qui optimise la qualite pour l'indexation (vs `"query"` qu'on utilisera
    en M4c pour la recherche).
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
            raise EmbeddingAuthError("Voyage api_key is required (got None)")
        if not texts:
            return []

        results: list[list[float]] = []
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=_TIMEOUT_SECONDS,
        ) as client:
            for batch_start in range(0, len(texts), _BATCH_SIZE):
                batch = texts[batch_start : batch_start + _BATCH_SIZE]
                results.extend(await self._embed_batch(client, batch))
        return results

    async def _embed_batch(
        self,
        client: httpx.AsyncClient,
        batch: list[str],
    ) -> list[list[float]]:
        for attempt in (0, 1):
            try:
                response = await client.post(
                    _VOYAGE_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": self._model,
                        "input": batch,
                        "input_type": "document",
                    },
                )
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt == 0:
                    log.warning("voyage.embed.network_retry", error=str(e))
                    await asyncio.sleep(self._retry_sleep)
                    continue
                raise EmbeddingProviderUnreachable(
                    f"Voyage unreachable: {type(e).__name__}: {e}"
                ) from e

            if response.status_code == 200:
                return self._parse_response(response.json())

            if response.status_code in (401, 403):
                raise EmbeddingAuthError(f"Voyage auth error: HTTP {response.status_code}")

            if response.status_code in (429, 503):
                if attempt == 0:
                    log.warning(
                        "voyage.embed.transient_retry",
                        status=response.status_code,
                    )
                    await asyncio.sleep(self._retry_sleep)
                    continue
                if response.status_code == 429:
                    raise EmbeddingRateLimited("Voyage rate limit (after retry)")
                raise EmbeddingProviderUnreachable("Voyage 503 (after retry)")

            raise EmbeddingProviderUnreachable(
                f"Voyage unexpected status: HTTP {response.status_code}"
            )

        raise EmbeddingProviderUnreachable("Voyage: retry loop exited unexpectedly")

    @staticmethod
    def _parse_response(payload: dict[str, Any]) -> list[list[float]]:
        items = payload.get("data", [])
        sorted_items = sorted(items, key=lambda x: x.get("index", 0))
        return [item["embedding"] for item in sorted_items]
