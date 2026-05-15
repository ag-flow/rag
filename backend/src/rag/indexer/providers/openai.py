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

_OPENAI_URL = "https://api.openai.com/v1/embeddings"
_BATCH_SIZE = 100
_TIMEOUT_SECONDS = 30.0
_DEFAULT_RETRY_SLEEP_SECONDS = 2.0


class OpenAIProvider:
    """Implémentation `EmbeddingProvider` pour l'API OpenAI Embeddings.

    Endpoint : `POST https://api.openai.com/v1/embeddings`.
    Batch jusqu'à 100 textes par call ; au-delà, boucle et concatène.
    Retry 1x sur HTTP 429/503/timeout après `retry_sleep_seconds`.
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
            raise EmbeddingAuthError("OpenAI api_key is required (got None)")
        if not texts:
            return []

        results: list[list[float]] = []
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=_TIMEOUT_SECONDS,
        ) as client:
            for batch_start in range(0, len(texts), _BATCH_SIZE):
                batch = texts[batch_start : batch_start + _BATCH_SIZE]
                batch_vectors = await self._embed_batch(client, batch)
                results.extend(batch_vectors)
        return results

    async def _embed_batch(
        self,
        client: httpx.AsyncClient,
        batch: list[str],
    ) -> list[list[float]]:
        """Embed un batch <= 100. Avec retry 1x sur 429/503/timeout."""
        for attempt in (0, 1):
            try:
                response = await client.post(
                    _OPENAI_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": self._model, "input": batch},
                )
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt == 0:
                    log.warning("openai.embed.network_retry", error=str(e))
                    await asyncio.sleep(self._retry_sleep)
                    continue
                raise EmbeddingProviderUnreachable(
                    f"OpenAI unreachable: {type(e).__name__}: {e}"
                ) from e

            if response.status_code == 200:
                return self._parse_response(response.json())

            if response.status_code in (401, 403):
                raise EmbeddingAuthError(f"OpenAI auth error: HTTP {response.status_code}")

            if response.status_code in (429, 503):
                if attempt == 0:
                    log.warning(
                        "openai.embed.transient_retry",
                        status=response.status_code,
                    )
                    await asyncio.sleep(self._retry_sleep)
                    continue
                if response.status_code == 429:
                    raise EmbeddingRateLimited("OpenAI rate limit (after retry)")
                raise EmbeddingProviderUnreachable("OpenAI 503 (after retry)")

            # Autre status non géré → unreachable générique
            raise EmbeddingProviderUnreachable(
                f"OpenAI unexpected status: HTTP {response.status_code}"
            )

        # Inaccessible (la boucle for retourne ou raise sur chaque iter), mais
        # le type checker veut un fallback.
        raise EmbeddingProviderUnreachable("OpenAI: retry loop exited unexpectedly")

    @staticmethod
    def _parse_response(payload: dict[str, Any]) -> list[list[float]]:
        """Extrait les embeddings triés par `index` (OpenAI les retourne déjà
        dans l'ordre mais on est défensif)."""
        items = payload.get("data", [])
        sorted_items = sorted(items, key=lambda x: x.get("index", 0))
        return [item["embedding"] for item in sorted_items]
