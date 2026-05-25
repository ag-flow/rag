from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from rag.indexer.providers.protocol import (
    EmbeddingProviderError,
    EmbeddingProviderUnreachable,
)

log = structlog.get_logger(__name__)

_TIMEOUT_SECONDS = 60.0  # LLMs locaux peuvent etre lents
_DEFAULT_RETRY_SLEEP_SECONDS = 5.0


class OllamaProvider:
    """Implementation `EmbeddingProvider` pour Ollama (LXC homelab).

    Endpoint : `POST <base_url>/api/embed` (API Ollama >= 0.3, stable).
    Pas d'auth (LXC local). 1 texte par call (l'API Ollama est mono-input).
    Boucle sequentielle pour preserver l'ordre - Ollama mono-thread CPU.

    Payload request  : {"model": "...", "input": "<text>"}
    Payload response : {"embeddings": [[...float...]]}
    """

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_sleep_seconds: float = _DEFAULT_RETRY_SLEEP_SECONDS,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._retry_sleep = retry_sleep_seconds

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float]] = []
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=_TIMEOUT_SECONDS,
        ) as client:
            for text in texts:
                results.append(await self._embed_one(client, text))
        return results

    async def _embed_one(
        self,
        client: httpx.AsyncClient,
        text: str,
    ) -> list[float]:
        for attempt in (0, 1):
            try:
                response = await client.post(
                    f"{self._base_url}/api/embed",
                    json={"model": self._model, "input": text},
                )
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt == 0:
                    log.warning("ollama.embed.network_retry", error=str(e))
                    await asyncio.sleep(self._retry_sleep)
                    continue
                raise EmbeddingProviderUnreachable(
                    f"Ollama unreachable: {type(e).__name__}: {e}"
                ) from e

            if response.status_code == 200:
                payload: dict[str, Any] = response.json()
                embeddings = payload.get("embeddings")
                if not isinstance(embeddings, list) or not embeddings:
                    raise EmbeddingProviderError("Ollama response missing 'embeddings' field")
                first = embeddings[0]
                if not isinstance(first, list):
                    raise EmbeddingProviderError("Ollama 'embeddings[0]' is not a list")
                return first

            if response.status_code == 503:
                if attempt == 0:
                    log.warning(
                        "ollama.embed.transient_retry",
                        status=response.status_code,
                    )
                    await asyncio.sleep(self._retry_sleep)
                    continue
                raise EmbeddingProviderUnreachable("Ollama 503 (after retry)")

            raise EmbeddingProviderUnreachable(
                f"Ollama unexpected status: HTTP {response.status_code}"
            )

        raise EmbeddingProviderUnreachable("Ollama: retry loop exited unexpectedly")

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        if not vectors:
            raise EmbeddingProviderUnreachable("Ollama returned empty embedding")
        return vectors[0]
