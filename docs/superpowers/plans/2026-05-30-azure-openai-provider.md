# Azure OpenAI Provider — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter le provider `azure-openai` pour l'indexation d'embeddings, permettant aux workspaces de rester dans l'infrastructure Azure sans envoyer de données à OpenAI en direct.

**Architecture:** Nouveau fichier `azure_openai.py` miroir de `openai.py`, avec deux différences : l'endpoint est `{base_url}/embeddings?api-version=2024-02-01` (base_url = URL complète du deployment Azure), et l'authentification utilise le header `api-key` (pas `Authorization: Bearer`). Le `model` n'est pas envoyé dans le payload (c'est le deployment qui définit le modèle côté Azure). Factory mise à jour, 3 lignes dans `model_dimensions`.

**Tech Stack:** Python 3.12 / httpx async / pytest-asyncio / asyncpg

---

## Structure des fichiers

### Créer
- `backend/migrations/026_azure_openai_models.sql`
- `backend/src/rag/indexer/providers/azure_openai.py`
- `backend/tests/unit/test_provider_azure_openai.py`

### Modifier
- `backend/src/rag/indexer/providers/factory.py` — ajouter le cas `azure-openai`
- `backend/tests/unit/test_provider_factory.py` — ajouter 2 tests azure-openai
- `specs/05-indexers.md` — commit (déjà modifié sur disque)
- `specs/12-rag-playground.md` — commit (déjà modifié sur disque)

---

## Task 1 : Commit specs + migration 026

**Files:**
- Modify: `specs/05-indexers.md` (déjà édité)
- Modify: `specs/12-rag-playground.md` (déjà édité)
- Create: `backend/migrations/026_azure_openai_models.sql`

- [ ] **Vérifier la branche**

```bash
git branch --show-current
```

Résultat attendu : `dev`

- [ ] **Créer la migration**

```sql
-- backend/migrations/026_azure_openai_models.sql
-- Migration 026 — modèles Azure OpenAI Embeddings

INSERT INTO model_dimensions (provider, model, dimension) VALUES
    ('azure-openai', 'text-embedding-3-small', 1536),
    ('azure-openai', 'text-embedding-3-large', 3072),
    ('azure-openai', 'text-embedding-ada-002', 1536)
ON CONFLICT DO NOTHING;
```

- [ ] **Commit specs + migration**

```bash
git add specs/05-indexers.md specs/12-rag-playground.md backend/migrations/026_azure_openai_models.sql
git commit -m "feat(db+specs): migration 026 azure-openai models + spec indexers"
```

---

## Task 2 : AzureOpenAIProvider (TDD)

**Files:**
- Create: `backend/tests/unit/test_provider_azure_openai.py`
- Create: `backend/src/rag/indexer/providers/azure_openai.py`

**Contexte Azure OpenAI Embeddings :**
- Endpoint : `POST {base_url}/embeddings?api-version=2024-02-01`
  où `base_url` = `https://{resource}.openai.azure.com/openai/deployments/{deployment_name}`
- Header auth : `api-key: {token}` (pas `Authorization: Bearer`)
- Payload request : `{"input": ["text1", "text2"]}` — pas de champ `model` (le deployment définit le modèle)
- Payload response : même format qu'OpenAI → `{"data": [{"embedding": [0.1, ...], "index": 0}]}`
- Batching : 100 textes max par call (même limite qu'OpenAI)
- Retry : 1 retry sur HTTP 429 / 503 / timeout (même stratégie qu'OpenAI)

### Étape 1 — Écrire les tests (rouge)

- [ ] **Créer `backend/tests/unit/test_provider_azure_openai.py`**

```python
from __future__ import annotations

import json

import httpx
import pytest

from rag.indexer.providers.azure_openai import AzureOpenAIProvider
from rag.indexer.providers.protocol import (
    EmbeddingAuthError,
    EmbeddingProviderUnreachable,
    EmbeddingRateLimited,
)

_BASE_URL = "https://myresource.openai.azure.com/openai/deployments/text-embedding-3-small"
_API_VERSION = "2024-02-01"


def _vec(dim: int = 1536, fill: float = 0.1) -> list[float]:
    return [fill] * dim


def _ok_response(texts: list[str]) -> httpx.Response:
    data = [{"embedding": _vec(), "index": i} for i in range(len(texts))]
    return httpx.Response(200, json={"data": data})


@pytest.mark.asyncio
async def test_azure_embed_texts_success() -> None:
    """Vérifie l'URL, le header api-key, l'absence de champ model dans le body."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return _ok_response(captured["body"]["input"])

    provider = AzureOpenAIProvider(
        base_url=_BASE_URL,
        api_key="az-test-key",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_texts(["hello", "world"])

    assert len(result) == 2
    assert len(result[0]) == 1536
    assert captured["url"] == f"{_BASE_URL}/embeddings?api-version={_API_VERSION}"
    assert captured["headers"]["api-key"] == "az-test-key"
    assert "authorization" not in captured["headers"]
    assert captured["body"]["input"] == ["hello", "world"]
    assert "model" not in captured["body"]


@pytest.mark.asyncio
async def test_azure_embed_texts_missing_api_key_raises_auth() -> None:
    provider = AzureOpenAIProvider(base_url=_BASE_URL, api_key=None)
    with pytest.raises(EmbeddingAuthError):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_azure_embed_empty_input_returns_empty() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"data": []})

    provider = AzureOpenAIProvider(
        base_url=_BASE_URL,
        api_key="az-key",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_texts([])
    assert result == []
    assert calls == 0


@pytest.mark.asyncio
async def test_azure_embed_texts_401_raises_auth_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Unauthorized"}})

    provider = AzureOpenAIProvider(
        base_url=_BASE_URL,
        api_key="az-bad",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingAuthError):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_azure_embed_texts_rate_limited_after_retry_raises() -> None:
    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(429, json={"error": {"message": "Rate limit"}})

    provider = AzureOpenAIProvider(
        base_url=_BASE_URL,
        api_key="az-key",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    with pytest.raises(EmbeddingRateLimited):
        await provider.embed_texts(["hello"])
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_azure_embed_texts_503_after_retry_raises_unreachable() -> None:
    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(503, json={"error": "Down"})

    provider = AzureOpenAIProvider(
        base_url=_BASE_URL,
        api_key="az-key",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    with pytest.raises(EmbeddingProviderUnreachable):
        await provider.embed_texts(["hello"])
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_azure_embed_texts_timeout_raises_unreachable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    provider = AzureOpenAIProvider(
        base_url=_BASE_URL,
        api_key="az-key",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    with pytest.raises(EmbeddingProviderUnreachable):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_azure_embed_texts_batches_over_100() -> None:
    batches_received: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        batches_received.append(len(body["input"]))
        data = [{"embedding": _vec(), "index": i} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": data})

    provider = AzureOpenAIProvider(
        base_url=_BASE_URL,
        api_key="az-key",
        transport=httpx.MockTransport(handler),
    )
    texts = [f"text-{i}" for i in range(150)]
    result = await provider.embed_texts(texts)
    assert len(result) == 150
    assert batches_received == [100, 50]


@pytest.mark.asyncio
async def test_azure_embed_query_returns_single_vector() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        data = [{"embedding": _vec(), "index": 0}]
        return httpx.Response(200, json={"data": data})

    provider = AzureOpenAIProvider(
        base_url=_BASE_URL,
        api_key="az-key",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_query("ma requête")
    assert len(result) == 1536
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_provider_azure_openai.py -v 2>&1 | head -10
```

Résultat attendu : `ImportError` (module inexistant).

### Étape 2 — Implémenter AzureOpenAIProvider

- [ ] **Créer `backend/src/rag/indexer/providers/azure_openai.py`**

```python
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
    """Implémentation `EmbeddingProvider` pour Azure OpenAI Embeddings.

    Endpoint : POST {base_url}/embeddings?api-version=2024-02-01
    où base_url = https://{resource}.openai.azure.com/openai/deployments/{deployment_name}

    Auth : header `api-key` (pas Authorization: Bearer).
    Le champ `model` n'est pas envoyé — le deployment Azure définit le modèle.
    Batch jusqu'à 100 textes ; retry 1x sur 429/503/timeout.
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

            raise EmbeddingProviderUnreachable(
                f"Azure OpenAI unexpected status: HTTP {response.status_code}"
            )

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
        items = payload.get("data", [])
        sorted_items = sorted(items, key=lambda x: x.get("index", 0))
        return [item["embedding"] for item in sorted_items]
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_provider_azure_openai.py -v
```

Résultat attendu : 9 tests PASS.

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/indexer/providers/azure_openai.py
```

Résultat attendu : aucune erreur.

- [ ] **Commit**

```bash
git add backend/src/rag/indexer/providers/azure_openai.py \
        backend/tests/unit/test_provider_azure_openai.py
git commit -m "feat(indexer): provider Azure OpenAI Embeddings"
```

---

## Task 3 : Factory + tests factory

**Files:**
- Modify: `backend/src/rag/indexer/providers/factory.py`
- Modify: `backend/tests/unit/test_provider_factory.py`

### Étape 1 — Ajouter les tests factory (rouge)

- [ ] **Ajouter dans `backend/tests/unit/test_provider_factory.py`**

Ajouter l'import en tête :

```python
from rag.indexer.providers.azure_openai import AzureOpenAIProvider
```

Ajouter les deux tests à la fin du fichier :

```python
def test_make_provider_azure_openai_returns_azure_instance() -> None:
    p = make_provider(
        provider="azure-openai",
        model="text-embedding-3-small",
        api_key="az-key",
        base_url="https://myresource.openai.azure.com/openai/deployments/text-embedding-3-small",
    )
    assert isinstance(p, AzureOpenAIProvider)


def test_make_provider_azure_openai_without_base_url_raises() -> None:
    with pytest.raises(ValueError, match="base_url"):
        make_provider(
            provider="azure-openai",
            model="text-embedding-3-small",
            api_key="az-key",
            base_url=None,
        )
```

- [ ] **Vérifier que les nouveaux tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_provider_factory.py::test_make_provider_azure_openai_returns_azure_instance tests/unit/test_provider_factory.py::test_make_provider_azure_openai_without_base_url_raises -v 2>&1 | head -15
```

Résultat attendu : FAILED (ValueError "Unsupported provider: 'azure-openai'").

### Étape 2 — Mettre à jour factory.py

- [ ] **Remplacer le contenu de `backend/src/rag/indexer/providers/factory.py`**

```python
from __future__ import annotations

from rag.indexer.providers.azure_openai import AzureOpenAIProvider
from rag.indexer.providers.jina import JinaProvider
from rag.indexer.providers.mistral import MistralProvider
from rag.indexer.providers.ollama import OllamaProvider
from rag.indexer.providers.openai import OpenAIProvider
from rag.indexer.providers.protocol import EmbeddingProvider
from rag.indexer.providers.voyage import VoyageProvider

_OLLAMA_DEFAULT_BASE_URL = "http://192.168.10.80:11434"


def make_provider(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
) -> EmbeddingProvider:
    """Dispatch sur le provider configuré pour un workspace.

    - `openai` / `voyage` / `mistral` / `jina` : `api_key` requis.
    - `azure-openai` : `api_key` + `base_url` requis
      (base_url = URL complète du deployment Azure).
    - `ollama` : `api_key` ignoré ; `base_url` fallback sur pve2 homelab.
    - Provider inconnu : `ValueError`.
    """
    if provider == "openai":
        return OpenAIProvider(model=model, api_key=api_key)
    if provider == "voyage":
        return VoyageProvider(model=model, api_key=api_key)
    if provider == "azure-openai":
        if not base_url:
            raise ValueError(
                "azure-openai provider requires base_url "
                "(https://{resource}.openai.azure.com/openai/deployments/{deployment_name})"
            )
        return AzureOpenAIProvider(base_url=base_url, api_key=api_key)
    if provider == "ollama":
        return OllamaProvider(
            model=model,
            base_url=base_url or _OLLAMA_DEFAULT_BASE_URL,
        )
    if provider == "mistral":
        return MistralProvider(model=model, api_key=api_key)
    if provider == "jina":
        return JinaProvider(model=model, api_key=api_key)
    raise ValueError(f"Unsupported provider: {provider!r}")
```

- [ ] **Vérifier que tous les tests factory passent**

```bash
cd backend && uv run pytest tests/unit/test_provider_factory.py -v
```

Résultat attendu : 7 tests PASS (5 existants + 2 nouveaux).

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/indexer/providers/factory.py
```

Résultat attendu : aucune erreur.

- [ ] **Commit**

```bash
git add backend/src/rag/indexer/providers/factory.py \
        backend/tests/unit/test_provider_factory.py
git commit -m "feat(indexer): factory azure-openai + tests"
```
