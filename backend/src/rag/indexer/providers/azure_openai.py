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

_API_VERSION = "2024-02-01"
_BATCH_SIZE = 100
_TIMEOUT_SECONDS = 30.0
_DEFAULT_RETRY_SLEEP_SECONDS = 2.0


class AzureOpenAIProvider:
    """Implementation `EmbeddingProvider` pour Azure OpenAI Embeddings.

    Endpoint : POST {base_url}/embeddings?api-version=2024-02-01
    ou base_url = https://{resource}.openai.azure.com/openai/deployments/{deployment_name}

    Auth : header `api-key` (pas Authorization: Bearer).
    Le champ `model` n'est pas envoye -- le deployment Azure definit le modele.
    Batch jusqu'a 100 textes ; retry 1x sur 429/503/timeout.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_sleep_seconds: float = _DEFAULT_RETRY_SLEEP_SECONDS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._transport = transport
        self._retry_sleep = retry_sleep_seconds

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self._api_key:
            raise EmbeddingAuthError("Azure OpenAI api_key is required (got None)")
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
        """Embed un batch <= 100. Avec retry 1x sur 429/503/timeout."""
        url = f"{self._base_url}/embeddings"
        params = {"api-version": _API_VERSION}

        for attempt in (0, 1):
            try:
                response = await client.post(
                    url,
                    params=params,
                    headers={"api-key": self._api_key},
                    json={"input": batch},
                )
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt == 0:
                    log.warning("azure_openai.embed.network_retry", error=str(e))
                    await asyncio.sleep(self._retry_sleep)
                    continue
                raise EmbeddingProviderUnreachable(
                    f"Azure OpenAI unreachable: {type(e).__name__}: {e}"
                ) from e

            if response.status_code == 200:
                return self._parse_response(response.json())

            if response.status_code in (401, 403):
                raise EmbeddingAuthError(
                    f"Azure OpenAI auth error: HTTP {response.status_code}"
                )

            if response.status_code in (429, 503):
                if attempt == 0:
                    log.warning(
                        "azure_openai.embed.transient_retry",
                        status=response.status_code,
                    )
                    await asyncio.sleep(self._retry_sleep)
                    continue
                if response.status_code == 429:
                    raise EmbeddingRateLimited("Azure OpenAI rate limit (after retry)")
                raise EmbeddingProviderUnreachable("Azure OpenAI 503 (after retry)")

            # Autre status non gere -> unreachable generique
            raise EmbeddingProviderUnreachable(
                f"Azure OpenAI unexpected status: HTTP {response.status_code}"
            )

        # Inaccessible (la boucle for retourne ou raise sur chaque iter), mais
        # le type checker veut un fallback.
        raise EmbeddingProviderUnreachable(
            "Azure OpenAI: retry loop exited unexpectedly"
        )

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        if not vectors:
            raise EmbeddingProviderUnreachable("Azure OpenAI returned empty embedding")
        return vectors[0]

    @staticmethod
    def _parse_response(payload: dict[str, Any]) -> list[list[float]]:
        """Extrait les embeddings tries par `index` (defensif)."""
        items = payload.get("data", [])
        sorted_items = sorted(items, key=lambda x: x.get("index", 0))
        return [item["embedding"] for item in sorted_items]
