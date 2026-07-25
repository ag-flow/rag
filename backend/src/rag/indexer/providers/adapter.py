# backend/src/rag/indexer/providers/adapter.py
from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
import structlog

from rag.indexer.providers.platforms.protocol import EmbeddingPlatform
from rag.indexer.providers.protocol import (
    EmbeddingAuthError,
    EmbeddingBadRequest,
    EmbeddingProviderUnreachable,
    EmbeddingQuotaExhausted,
    EmbeddingRateLimited,
)
from rag.indexer.providers.services.protocol import EmbeddingService

log = structlog.get_logger(__name__)

_TIMEOUT_SECONDS = 30.0
_DEFAULT_RETRY_SLEEP_SECONDS = 2.0
# Nombre de retries sur transitoire (429/503/réseau) → _MAX_RETRIES + 1 tentatives.
_MAX_RETRIES = 3
# Plafond d'une pause unique, y compris un Retry-After élevé.
_MAX_RETRY_SLEEP_SECONDS = 60.0


def _parse_retry_after(value: str | None) -> float | None:
    """Parse un header `Retry-After` : delta-seconds ou HTTP-date.

    Retourne le délai en secondes (>= 0), ou None si absent/invalide.
    """
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(int(value)))
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return max(0.0, (dt - datetime.now(UTC)).total_seconds())


class EmbeddingProviderAdapter:
    """Compose EmbeddingService + EmbeddingPlatform → implémente EmbeddingProvider.

    Responsabilités : batching, HTTP retry par batch avec backoff exponentiel
    jitteré honorant `Retry-After` (429/503/timeout), error mapping.
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

    def _retry_delay(self, attempt: int, retry_after: float | None) -> float:
        """Backoff exponentiel full-jitter, plancher `Retry-After`, plafond global.

        Base = retry_sleep · 2^attempt ; le jitter tire uniformément dans
        [0, base] (évite le thundering herd) ; `Retry-After` (si fourni par le
        provider) sert de plancher ; le tout est plafonné à _MAX_RETRY_SLEEP.
        """
        base = self._retry_sleep * (2**attempt)
        jittered = random.uniform(0.0, base)  # noqa: S311 — jitter de retry, pas de crypto
        delay = max(jittered, retry_after or 0.0)
        return min(delay, _MAX_RETRY_SLEEP_SECONDS)

    async def _call(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> list[list[float]]:
        for attempt in range(_MAX_RETRIES + 1):
            is_last = attempt == _MAX_RETRIES
            try:
                response = await client.post(url, headers=headers, json=payload)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if is_last:
                    raise EmbeddingProviderUnreachable(
                        f"Unreachable: {type(e).__name__}: {e}"
                    ) from e
                delay = self._retry_delay(attempt, None)
                log.warning(
                    "embedding_adapter.network_retry",
                    error=str(e),
                    attempt=attempt,
                    sleep=round(delay, 3),
                )
                await asyncio.sleep(delay)
                continue

            # Contexte systématique des erreurs : le message du job doit dire
            # QUEL service d'embedding est appelé (URL + modèle), pas juste un
            # code HTTP muet.
            ctx = f"service d'embedding {url} (modèle '{self._model}')"
            if response.status_code == 200:
                return self._service.parse_response(response.json())
            if response.status_code == 402:
                raise EmbeddingQuotaExhausted(f"{ctx} : quota épuisé (HTTP 402)")
            if response.status_code in (401, 403):
                raise EmbeddingAuthError(
                    f"{ctx} : authentification refusée (HTTP {response.status_code})"
                )
            if response.status_code in (429, 503):
                if is_last:
                    if response.status_code == 429:
                        raise EmbeddingRateLimited(f"{ctx} : rate limit (après retries)")
                    raise EmbeddingProviderUnreachable(f"{ctx} : HTTP 503 (après retries)")
                retry_after = _parse_retry_after(response.headers.get("retry-after"))
                delay = self._retry_delay(attempt, retry_after)
                log.warning(
                    "embedding_adapter.transient_retry",
                    status=response.status_code,
                    attempt=attempt,
                    retry_after=retry_after,
                    sleep=round(delay, 3),
                )
                await asyncio.sleep(delay)
                continue
            if 400 <= response.status_code < 500:
                # Le corps porte la cause exploitable (ex. Ollama 404 :
                # « model 'x' not found, try pulling it first »).
                detail = response.text[:200].strip()
                raise EmbeddingBadRequest(
                    f"{ctx} : HTTP {response.status_code}"
                    + (f" — {detail}" if detail else "")
                )
            raise EmbeddingProviderUnreachable(
                f"{ctx} : HTTP {response.status_code} inattendu"
            )

        raise EmbeddingProviderUnreachable("Retry loop exited unexpectedly")
