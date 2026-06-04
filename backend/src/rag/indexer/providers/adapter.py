# backend/src/rag/indexer/providers/adapter.py
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from rag.indexer.providers.platforms.protocol import EmbeddingPlatform
from rag.indexer.providers.protocol import (
    EmbeddingAuthError,
    EmbeddingProviderUnreachable,
    EmbeddingRateLimited,
)
from rag.indexer.providers.services.protocol import EmbeddingService

log = structlog.get_logger(__name__)

_TIMEOUT_SECONDS = 30.0
_DEFAULT_RETRY_SLEEP_SECONDS = 2.0


class EmbeddingProviderAdapter:
    """Compose EmbeddingService + EmbeddingPlatform → implémente EmbeddingProvider.

    Responsabilités : batching, HTTP retry 1x (429/503/timeout), error mapping.
    """

    def __init__(
        self,
        *,
        service: EmbeddingService,
        platform: EmbeddingPlatform,
        model: str,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_sleep_seconds: float = _DEFAULT_RETRY_SLEEP_SECONDS,
    ) -> None:
        self._service = service
        self._platform = platform
        self._model = model
        self._transport = transport
        self._retry_sleep = retry_sleep_seconds

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self._platform.validate_auth()
        if not texts:
            return []
        results: list[list[float]] = []
        async with httpx.AsyncClient(
            transport=self._transport, timeout=_TIMEOUT_SECONDS
        ) as client:
            for i in range(0, len(texts), self._service.batch_size):
                batch = texts[i : i + self._service.batch_size]
                results.extend(await self._embed_batch(client, batch))
        return results

    async def embed_query(self, text: str) -> list[float]:
        self._platform.validate_auth()
        payload = self._platform.modify_payload(
            self._service.build_query_payload(text, self._model)
        )
        url = self._platform.url(self._service.embeddings_path)
        headers = self._platform.auth_headers()
        async with httpx.AsyncClient(
            transport=self._transport, timeout=_TIMEOUT_SECONDS
        ) as client:
            vectors = await self._call(client, url, headers, payload)
        if not vectors:
            raise EmbeddingProviderUnreachable("Empty embedding returned for query")
        return vectors[0]

    async def _embed_batch(
        self, client: httpx.AsyncClient, batch: list[str]
    ) -> list[list[float]]:
        payload = self._platform.modify_payload(
            self._service.build_document_payload(batch, self._model)
        )
        url = self._platform.url(self._service.embeddings_path)
        headers = self._platform.auth_headers()
        return await self._call(client, url, headers, payload)

    async def _call(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> list[list[float]]:
        for attempt in (0, 1):
            try:
                response = await client.post(url, headers=headers, json=payload)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt == 0:
                    log.warning("embedding_adapter.network_retry", error=str(e))
                    await asyncio.sleep(self._retry_sleep)
                    continue
                raise EmbeddingProviderUnreachable(
                    f"Unreachable: {type(e).__name__}: {e}"
                ) from e

            if response.status_code == 200:
                return self._service.parse_response(response.json())
            if response.status_code in (401, 403):
                raise EmbeddingAuthError(f"Auth error: HTTP {response.status_code}")
            if response.status_code in (429, 503):
                if attempt == 0:
                    log.warning(
                        "embedding_adapter.transient_retry",
                        status=response.status_code,
                    )
                    await asyncio.sleep(self._retry_sleep)
                    continue
                if response.status_code == 429:
                    raise EmbeddingRateLimited("Rate limit (after retry)")
                raise EmbeddingProviderUnreachable("503 (after retry)")
            raise EmbeddingProviderUnreachable(
                f"Unexpected HTTP {response.status_code}"
            )

        raise EmbeddingProviderUnreachable("Retry loop exited unexpectedly")
