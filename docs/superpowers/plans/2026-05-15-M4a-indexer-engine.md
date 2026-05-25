# M4a — Indexer Engine effectif · Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer `NoOpIndexer` (stub M3) par un `RealIndexer` qui réalise effectivement le chunking + l'embedding via 3 providers (OpenAI, Voyage AI, Ollama) + l'upsert pgvector dans la base `rag_<workspace>` dédiée. Le `SyncWorker` (M3) consomme l'`IndexerProtocol` inchangé.

**Architecture:** `RealIndexer` orchestre `chunking.chunk_text` (split paragraphe + max 2000 chars + overlap 200), un `EmbeddingProvider` (Protocol + 3 implémentations + factory) pour générer les vecteurs, et `db/workspace_embeddings.upsert_chunks` (DELETE + INSERT batch en transaction). Le lifespan FastAPI remplace l'injection `NoOpIndexer` par `RealIndexer` sans toucher au `SyncWorker`.

**Tech Stack:** Python 3.12 · asyncpg · httpx (AsyncClient) · pgvector>=0.3 · structlog · pytest + pytest-asyncio · OpenAI / Voyage AI / Ollama HTTP APIs.

**Référence design :** `docs/superpowers/specs/2026-05-15-M4a-indexer-engine-design.md`.

---

## Convention d'exécution

- Toutes les commandes sont à exécuter depuis `E:\srcs\ag-flow.rag\backend\` sauf indication contraire.
- Sur Windows local, utiliser PowerShell ; sur LXC 303, bash.
- Chaque task se termine par un commit en français conventionnel sur la branche `dev`.
- Aucune livraison sur LXC avant la **Task 12** (smoke deploy final).
- Tests d'intégration : `$env:TEST_POSTGRES_PASSWORD = "i22BfVjVnEG1FhKL0sJ1CuznH73twl1J"` (Postgres LXC 303 — password actuel ; si reset entre temps, lire `/opt/rag/.env` sur LXC).
- Tests smoke : opt-in via `@pytest.mark.smoke`, **skippés par défaut**. Ils requièrent `OPENAI_API_KEY_TEST`, `VOYAGE_API_KEY_TEST`, `OLLAMA_TEST_URL` en env vars.

---

## Task 1 — Ajouter `pgvector>=0.3` aux dépendances

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock` (généré)

- [ ] **Step 1.1 : Ajouter la dépendance**

Dans `backend/pyproject.toml`, dans la section `[project]` → `dependencies`, ajouter `pgvector>=0.3` après `harpocrate` :

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "asyncpg>=0.30",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "structlog>=24.4",
    "httpx>=0.27",
    "bcrypt>=4.2",
    "python-multipart>=0.0.20",
    "harpocrate",
    "pgvector>=0.3",
]
```

- [ ] **Step 1.2 : `uv sync` pour régénérer le lock**

```powershell
Set-Location E:\srcs\ag-flow.rag\backend
uv sync
```

Vérifier que `pgvector` est installé :

```powershell
uv pip list | Select-String pgvector
```

Attendu : `pgvector  0.3.x` (ou plus récent).

- [ ] **Step 1.3 : Vérifier que les tests existants passent toujours**

```powershell
$env:TEST_POSTGRES_PASSWORD = "i22BfVjVnEG1FhKL0sJ1CuznH73twl1J"
uv run pytest -q
```

Aucune régression attendue (M3 tests doivent rester verts).

- [ ] **Step 1.4 : Commit**

```bash
git add backend/pyproject.toml backend/uv.lock
git commit -m "chore(deps): ajoute pgvector>=0.3 (sérialisation vector pour M4a)"
```

NE PAS pusher.

---

## Task 2 — `indexer/chunking.py` : `chunk_text`

**Files:**
- Create: `backend/src/rag/indexer/chunking.py`
- Create: `backend/tests/unit/test_chunking.py`

- [ ] **Step 2.1 : Tests (rouge)**

Créer `backend/tests/unit/test_chunking.py` :

```python
from __future__ import annotations

import pytest

from rag.indexer.chunking import chunk_text


def test_chunk_text_empty_returns_empty() -> None:
    assert chunk_text("") == []


def test_chunk_text_whitespace_only_returns_empty() -> None:
    assert chunk_text("   \n\n   \n\n   ") == []


def test_chunk_text_short_content_returns_single_chunk() -> None:
    content = "hello world"
    result = chunk_text(content)
    assert result == ["hello world"]


def test_chunk_text_two_short_paragraphs_are_coalesced() -> None:
    # Deux paragraphes courts (< min_chars) → coalescés en 1 chunk
    content = "Paragraphe un.\n\nParagraphe deux."
    result = chunk_text(content)
    assert len(result) == 1
    assert "Paragraphe un." in result[0]
    assert "Paragraphe deux." in result[0]


def test_chunk_text_two_long_paragraphs_split_with_overlap() -> None:
    # Deux paragraphes > max_chars → 2+ chunks avec overlap
    para_a = "A" * 1500
    para_b = "B" * 1500
    content = f"{para_a}\n\n{para_b}"
    result = chunk_text(content, max_chars=2000, min_chars=200, overlap_chars=200)
    assert len(result) >= 2
    # Overlap : le chunk[i+1] doit contenir au moins une partie de la fin de chunk[i]
    for i in range(1, len(result)):
        # Au moins overlap_chars chars en commun en fin/début
        assert any(
            result[i].startswith(result[i - 1][-k:])
            for k in range(50, 201)
        )


def test_chunk_text_single_giant_paragraph_split_on_separator() -> None:
    # 1 paragraphe géant (3000 chars) → split sur séparateur naturel
    content = ("Phrase courte. " * 200)  # ~3000 chars, plein de ". "
    result = chunk_text(content, max_chars=2000, min_chars=200, overlap_chars=200)
    assert len(result) >= 2
    # Chaque chunk <= max_chars + overlap_chars
    for chunk in result:
        assert len(chunk) <= 2200


def test_chunk_text_code_no_paragraph_splits_on_newline() -> None:
    # Code sans `\n\n` → fallback sur `\n`
    content = "\n".join([f"line {i}" for i in range(500)])  # ~3500 chars
    result = chunk_text(content, max_chars=2000)
    assert len(result) >= 2


def test_chunk_text_overlap_too_large_raises() -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_text("hello", max_chars=100, overlap_chars=150)


def test_chunk_text_strips_outer_whitespace() -> None:
    content = "\n\n   hello   \n\n"
    result = chunk_text(content)
    assert result == ["hello"]


def test_chunk_text_preserves_content_when_short() -> None:
    content = "Multi-line\ncontent\nwith newlines"
    result = chunk_text(content)
    # Sous min_chars → 1 chunk avec contenu intact (modulo strip outer ws)
    assert len(result) == 1
    assert result[0] == content
```

- [ ] **Step 2.2 : Lancer (rouge)**

```powershell
uv run pytest tests/unit/test_chunking.py -v
```

Attendu : 10 ERROR `ModuleNotFoundError: rag.indexer.chunking`.

- [ ] **Step 2.3 : Impl**

Créer `backend/src/rag/indexer/chunking.py` :

```python
from __future__ import annotations

import re


def chunk_text(
    content: str,
    *,
    max_chars: int = 2000,
    min_chars: int = 200,
    overlap_chars: int = 200,
) -> list[str]:
    """Découpe `content` en chunks de ~max_chars, avec overlap entre chunks.

    Algorithme :
      1. Split sur `\\n\\n` (paragraphes) ; strip + retire vides.
      2. Coalesce paragraphes < min_chars avec le suivant tant que la
         concaténation reste ≤ max_chars.
      3. Split paragraphes > max_chars sur un séparateur naturel
         (`. `, `\\n`, ` `) cherché dans la fenêtre [max_chars - 200, max_chars] ;
         à défaut, coupe brutalement à max_chars.
      4. Ajoute overlap_chars chars en tête de chaque chunk (sauf le premier),
         pris en fin du précédent.

    Cas particuliers :
      - content vide ou whitespace-only → []
      - 1 paragraphe court → [content_stripped]
      - Code sans `\\n\\n` → fallback split sur `\\n`
      - overlap_chars >= max_chars → ValueError
    """
    if overlap_chars >= max_chars:
        raise ValueError(
            f"overlap_chars ({overlap_chars}) must be < max_chars ({max_chars})"
        )

    stripped = content.strip()
    if not stripped:
        return []

    # 1. Split paragraphes
    paragraphs = [p.strip() for p in stripped.split("\n\n") if p.strip()]

    # Fallback : si pas de `\n\n`, split sur `\n` quand le bloc est trop grand.
    if len(paragraphs) == 1 and len(paragraphs[0]) > max_chars:
        paragraphs = [p for p in paragraphs[0].split("\n") if p.strip()]

    # 2. Coalesce les petits paragraphes
    coalesced: list[str] = []
    buffer = ""
    for p in paragraphs:
        if not buffer:
            buffer = p
            continue
        if len(buffer) < min_chars and len(buffer) + 2 + len(p) <= max_chars:
            buffer = f"{buffer}\n\n{p}"
        else:
            coalesced.append(buffer)
            buffer = p
    if buffer:
        coalesced.append(buffer)

    # 3. Split les gros paragraphes
    split_chunks: list[str] = []
    for p in coalesced:
        if len(p) <= max_chars:
            split_chunks.append(p)
            continue
        split_chunks.extend(_split_big_paragraph(p, max_chars))

    # 4. Ajout d'overlap
    if overlap_chars <= 0 or len(split_chunks) <= 1:
        return split_chunks

    overlapped: list[str] = [split_chunks[0]]
    for i in range(1, len(split_chunks)):
        prev_tail = split_chunks[i - 1][-overlap_chars:]
        overlapped.append(prev_tail + split_chunks[i])
    return overlapped


def _split_big_paragraph(p: str, max_chars: int) -> list[str]:
    """Split un paragraphe > max_chars sur un séparateur naturel."""
    chunks: list[str] = []
    remaining = p
    while len(remaining) > max_chars:
        # Cherche un séparateur dans [max_chars - 200, max_chars]
        window_start = max(0, max_chars - 200)
        window = remaining[window_start:max_chars]
        cut_pos = -1
        # Préférence : `. `, `\n`, ` `
        for sep in (". ", "\n", " "):
            idx = window.rfind(sep)
            if idx != -1:
                cut_pos = window_start + idx + len(sep)
                break
        if cut_pos == -1:
            cut_pos = max_chars  # coupe brutalement
        chunks.append(remaining[:cut_pos].strip())
        remaining = remaining[cut_pos:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks
```

- [ ] **Step 2.4 : Lancer (vert)**

```powershell
uv run pytest tests/unit/test_chunking.py -v
```

10 PASS.

- [ ] **Step 2.5 : Lint + mypy**

```powershell
uv run ruff check src/rag/indexer/chunking.py tests/unit/test_chunking.py
uv run ruff format --check src/rag/indexer/chunking.py tests/unit/test_chunking.py
uv run mypy src/rag/indexer/chunking.py
```

Tout clean.

- [ ] **Step 2.6 : Commit**

```bash
git add backend/src/rag/indexer/chunking.py backend/tests/unit/test_chunking.py
git commit -m "feat(indexer): chunk_text (paragraphe + max chars + overlap)"
```

NE PAS pusher.

---

## Task 3 — `indexer/providers/protocol.py` : `EmbeddingProvider` + exceptions

**Files:**
- Create: `backend/src/rag/indexer/providers/__init__.py` (vide)
- Create: `backend/src/rag/indexer/providers/protocol.py`
- Create: `backend/tests/unit/test_provider_protocol.py`

- [ ] **Step 3.1 : Tests (rouge)**

Créer `backend/tests/unit/test_provider_protocol.py` :

```python
from __future__ import annotations

import inspect

import pytest

from rag.indexer.providers.protocol import (
    EmbeddingAuthError,
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingProviderUnreachable,
    EmbeddingRateLimited,
)


def test_embedding_provider_protocol_has_embed_texts() -> None:
    """Le Protocol définit bien `embed_texts(texts) -> list[list[float]]` async."""
    method = inspect.getattr_static(EmbeddingProvider, "embed_texts")
    assert inspect.iscoroutinefunction(method)


def test_exception_hierarchy() -> None:
    """Toutes les exceptions provider héritent de EmbeddingProviderError."""
    assert issubclass(EmbeddingAuthError, EmbeddingProviderError)
    assert issubclass(EmbeddingRateLimited, EmbeddingProviderError)
    assert issubclass(EmbeddingProviderUnreachable, EmbeddingProviderError)
    assert issubclass(EmbeddingProviderError, RuntimeError)


def test_embedding_auth_error_can_be_raised_and_caught() -> None:
    with pytest.raises(EmbeddingProviderError):
        raise EmbeddingAuthError("401 unauthorized")


def test_embedding_rate_limited_can_be_raised_and_caught() -> None:
    with pytest.raises(EmbeddingProviderError):
        raise EmbeddingRateLimited("429 too many")


def test_embedding_provider_unreachable_can_be_raised_and_caught() -> None:
    with pytest.raises(EmbeddingProviderError):
        raise EmbeddingProviderUnreachable("timeout")
```

- [ ] **Step 3.2 : Lancer (rouge)**

```powershell
uv run pytest tests/unit/test_provider_protocol.py -v
```

5 ERROR `ModuleNotFoundError`.

- [ ] **Step 3.3 : Impl**

Créer `backend/src/rag/indexer/providers/__init__.py` (vide) :

```python
```

Créer `backend/src/rag/indexer/providers/protocol.py` :

```python
from __future__ import annotations

from typing import Protocol


class EmbeddingProviderError(RuntimeError):
    """Base des erreurs provider d'embedding.

    Les sous-classes distinguent les causes courantes pour permettre au
    SyncWorker (M3) d'écrire un `error_message` typé dans `index_jobs`.
    """


class EmbeddingAuthError(EmbeddingProviderError):
    """HTTP 401/403 — API key invalide ou révoquée."""


class EmbeddingRateLimited(EmbeddingProviderError):
    """HTTP 429 — le quota a été atteint et le retry interne a échoué."""


class EmbeddingProviderUnreachable(EmbeddingProviderError):
    """Réseau down, timeout, ou HTTP 503 (provider en panne)."""


class EmbeddingProvider(Protocol):
    """Frontière commune entre `RealIndexer` (M4a) et les implémentations
    OpenAI / Voyage / Ollama.

    Chaque provider expose une seule méthode async : `embed_texts(texts)`.
    Les batchs internes (max 100 pour OpenAI/Voyage, 1 pour Ollama) sont
    une décision d'implémentation invisible côté caller.
    """

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Retourne 1 vecteur (list[float]) par texte d'entrée, dans le
        même ordre que `texts`.

        Lève `EmbeddingProviderError` (ou sous-classe) sur échec.
        """
        ...
```

- [ ] **Step 3.4 : Lancer (vert)**

```powershell
uv run pytest tests/unit/test_provider_protocol.py -v
```

5 PASS.

- [ ] **Step 3.5 : Lint + mypy**

```powershell
uv run ruff check src/rag/indexer/providers/protocol.py tests/unit/test_provider_protocol.py
uv run ruff format --check src/rag/indexer/providers/protocol.py tests/unit/test_provider_protocol.py
uv run mypy src/rag/indexer/providers/protocol.py
```

Clean.

- [ ] **Step 3.6 : Commit**

```bash
git add backend/src/rag/indexer/providers/__init__.py backend/src/rag/indexer/providers/protocol.py backend/tests/unit/test_provider_protocol.py
git commit -m "feat(indexer/providers): EmbeddingProvider Protocol + 4 exceptions typées"
```

NE PAS pusher.

---

## Task 4 — `providers/openai.py` : `OpenAIProvider`

**Files:**
- Create: `backend/src/rag/indexer/providers/openai.py`
- Create: `backend/tests/unit/test_provider_openai.py`

- [ ] **Step 4.1 : Tests (rouge)**

Créer `backend/tests/unit/test_provider_openai.py` :

```python
from __future__ import annotations

import json

import httpx
import pytest

from rag.indexer.providers.openai import OpenAIProvider
from rag.indexer.providers.protocol import (
    EmbeddingAuthError,
    EmbeddingProviderUnreachable,
    EmbeddingRateLimited,
)


def _vec(dim: int = 1536, fill: float = 0.1) -> list[float]:
    return [fill] * dim


def _ok_response(texts: list[str]) -> httpx.Response:
    data = [{"embedding": _vec(), "index": i} for i in range(len(texts))]
    return httpx.Response(200, json={"data": data, "model": "text-embedding-3-small"})


@pytest.mark.asyncio
async def test_openai_embed_texts_success() -> None:
    captured_request: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["headers"] = dict(request.headers)
        captured_request["body"] = json.loads(request.content)
        return _ok_response(captured_request["body"]["input"])

    transport = httpx.MockTransport(handler)
    provider = OpenAIProvider(
        model="text-embedding-3-small", api_key="sk-test", transport=transport,
    )
    result = await provider.embed_texts(["hello", "world"])
    assert len(result) == 2
    assert len(result[0]) == 1536
    assert captured_request["url"] == "https://api.openai.com/v1/embeddings"
    assert captured_request["headers"]["authorization"] == "Bearer sk-test"
    assert captured_request["body"]["model"] == "text-embedding-3-small"
    assert captured_request["body"]["input"] == ["hello", "world"]


@pytest.mark.asyncio
async def test_openai_embed_texts_auth_error_raises_typed() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    provider = OpenAIProvider(
        model="text-embedding-3-small", api_key="sk-bad",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingAuthError):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_openai_embed_texts_rate_limited_after_retry_raises() -> None:
    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(429, json={"error": {"message": "Rate limit"}})

    provider = OpenAIProvider(
        model="text-embedding-3-small", api_key="sk-x",
        transport=httpx.MockTransport(handler), retry_sleep_seconds=0,
    )
    with pytest.raises(EmbeddingRateLimited):
        await provider.embed_texts(["hello"])
    # 1 call initial + 1 retry = 2 appels
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_openai_embed_texts_batches_over_100() -> None:
    """Si > 100 textes, OpenAIProvider doit faire 2+ calls et concat dans l'ordre."""
    batches_received: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        batches_received.append(len(body["input"]))
        data = [{"embedding": _vec(), "index": i} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": data})

    provider = OpenAIProvider(
        model="text-embedding-3-small", api_key="sk-x",
        transport=httpx.MockTransport(handler),
    )
    texts = [f"text-{i}" for i in range(150)]
    result = await provider.embed_texts(texts)
    assert len(result) == 150
    # 2 batches : 100 + 50
    assert batches_received == [100, 50]


@pytest.mark.asyncio
async def test_openai_embed_texts_timeout_raises_unreachable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    provider = OpenAIProvider(
        model="text-embedding-3-small", api_key="sk-x",
        transport=httpx.MockTransport(handler), retry_sleep_seconds=0,
    )
    with pytest.raises(EmbeddingProviderUnreachable):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_openai_embed_texts_missing_api_key_raises_auth() -> None:
    provider = OpenAIProvider(model="text-embedding-3-small", api_key=None)
    with pytest.raises(EmbeddingAuthError):
        await provider.embed_texts(["hello"])
```

- [ ] **Step 4.2 : Lancer (rouge)**

```powershell
Set-Location E:\srcs\ag-flow.rag\backend
uv run pytest tests/unit/test_provider_openai.py -v
```

6 ERROR `ModuleNotFoundError`.

- [ ] **Step 4.3 : Impl**

Créer `backend/src/rag/indexer/providers/openai.py` :

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

_OPENAI_URL = "https://api.openai.com/v1/embeddings"
_BATCH_SIZE = 100
_TIMEOUT_SECONDS = 30.0
_DEFAULT_RETRY_SLEEP_SECONDS = 2.0


class OpenAIProvider:
    """Implémentation `EmbeddingProvider` pour l'API OpenAI Embeddings.

    Endpoint : `POST https://api.openai.com/v1/embeddings`.
    Batch jusqu'à 100 textes par call ; au-delà, boucle et concatène.
    Retry 1× sur HTTP 429/503/timeout après `retry_sleep_seconds`.
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        transport: httpx.BaseTransport | None = None,
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
            transport=self._transport, timeout=_TIMEOUT_SECONDS,
        ) as client:
            for batch_start in range(0, len(texts), _BATCH_SIZE):
                batch = texts[batch_start : batch_start + _BATCH_SIZE]
                batch_vectors = await self._embed_batch(client, batch)
                results.extend(batch_vectors)
        return results

    async def _embed_batch(
        self, client: httpx.AsyncClient, batch: list[str],
    ) -> list[list[float]]:
        """Embed un batch ≤ 100. Avec retry 1× sur 429/503/timeout."""
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
                raise EmbeddingAuthError(
                    f"OpenAI auth error: HTTP {response.status_code}"
                )

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
                raise EmbeddingProviderUnreachable(
                    "OpenAI 503 (after retry)"
                )

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
```

- [ ] **Step 4.4 : Lancer (vert)**

```powershell
uv run pytest tests/unit/test_provider_openai.py -v
```

6 PASS.

- [ ] **Step 4.5 : Lint + mypy**

```powershell
uv run ruff check src/rag/indexer/providers/openai.py tests/unit/test_provider_openai.py
uv run ruff format --check src/rag/indexer/providers/openai.py tests/unit/test_provider_openai.py
uv run mypy src/rag/indexer/providers/openai.py
```

Clean.

- [ ] **Step 4.6 : Commit**

```bash
git add backend/src/rag/indexer/providers/openai.py backend/tests/unit/test_provider_openai.py
git commit -m "feat(indexer/providers): OpenAIProvider (batch 100 + retry 1× sur 429/503/timeout)"
```

NE PAS pusher.

---

## Task 5 — `providers/voyage.py` : `VoyageProvider`

**Files:**
- Create: `backend/src/rag/indexer/providers/voyage.py`
- Create: `backend/tests/unit/test_provider_voyage.py`

- [ ] **Step 5.1 : Tests (rouge)**

Créer `backend/tests/unit/test_provider_voyage.py` :

```python
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
        data = [
            {"embedding": _vec(), "index": i}
            for i in range(len(captured["body"]["input"]))
        ]
        return httpx.Response(200, json={"data": data})

    provider = VoyageProvider(
        model="voyage-3", api_key="vk-test",
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
```

- [ ] **Step 5.2 : Lancer (rouge)**

```powershell
uv run pytest tests/unit/test_provider_voyage.py -v
```

2 ERROR.

- [ ] **Step 5.3 : Impl**

Créer `backend/src/rag/indexer/providers/voyage.py` :

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

_VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
_BATCH_SIZE = 128
_TIMEOUT_SECONDS = 30.0
_DEFAULT_RETRY_SLEEP_SECONDS = 2.0


class VoyageProvider:
    """Implémentation `EmbeddingProvider` pour Voyage AI.

    Endpoint : `POST https://api.voyageai.com/v1/embeddings`.
    Batch jusqu'à 128 textes (limite Voyage), avec `input_type="document"`
    qui optimise la qualité pour l'indexation (vs `"query"` qu'on utilisera
    en M4c pour la recherche).
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        transport: httpx.BaseTransport | None = None,
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
            transport=self._transport, timeout=_TIMEOUT_SECONDS,
        ) as client:
            for batch_start in range(0, len(texts), _BATCH_SIZE):
                batch = texts[batch_start : batch_start + _BATCH_SIZE]
                results.extend(await self._embed_batch(client, batch))
        return results

    async def _embed_batch(
        self, client: httpx.AsyncClient, batch: list[str],
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
                raise EmbeddingAuthError(
                    f"Voyage auth error: HTTP {response.status_code}"
                )

            if response.status_code in (429, 503):
                if attempt == 0:
                    log.warning(
                        "voyage.embed.transient_retry", status=response.status_code,
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
```

- [ ] **Step 5.4 : Vert + lint + commit**

```powershell
uv run pytest tests/unit/test_provider_voyage.py -v
uv run ruff check src/rag/indexer/providers/voyage.py tests/unit/test_provider_voyage.py
uv run mypy src/rag/indexer/providers/voyage.py
```

2 PASS + clean.

```bash
git add backend/src/rag/indexer/providers/voyage.py backend/tests/unit/test_provider_voyage.py
git commit -m "feat(indexer/providers): VoyageProvider (input_type=document, batch 128)"
```

---

## Task 6 — `providers/ollama.py` : `OllamaProvider`

**Files:**
- Create: `backend/src/rag/indexer/providers/ollama.py`
- Create: `backend/tests/unit/test_provider_ollama.py`

- [ ] **Step 6.1 : Tests (rouge)**

Créer `backend/tests/unit/test_provider_ollama.py` :

```python
from __future__ import annotations

import json

import httpx
import pytest

from rag.indexer.providers.ollama import OllamaProvider


def _vec(dim: int = 768, fill: float = 0.3) -> list[float]:
    return [fill] * dim


@pytest.mark.asyncio
async def test_ollama_embed_texts_calls_once_per_input() -> None:
    """L'API Ollama /api/embeddings est mono-input : on doit boucler."""
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, json={"embedding": _vec()})

    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://test.local:11434",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_texts(["hello", "world", "foo"])
    assert len(result) == 3
    assert len(calls) == 3
    assert calls[0]["model"] == "nomic-embed-text"
    assert calls[0]["prompt"] == "hello"
    assert calls[1]["prompt"] == "world"
    assert calls[2]["prompt"] == "foo"


@pytest.mark.asyncio
async def test_ollama_embed_texts_uses_base_url() -> None:
    captured_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        return httpx.Response(200, json={"embedding": _vec()})

    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://my-ollama.example:9999",
        transport=httpx.MockTransport(handler),
    )
    await provider.embed_texts(["hello"])
    assert captured_urls == ["http://my-ollama.example:9999/api/embeddings"]


@pytest.mark.asyncio
async def test_ollama_embed_empty_input_returns_empty() -> None:
    """Pas d'appel HTTP si input vide."""
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"embedding": _vec()})

    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://x:1",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_texts([])
    assert result == []
    assert calls == 0
```

- [ ] **Step 6.2 : Lancer (rouge)**

```powershell
uv run pytest tests/unit/test_provider_ollama.py -v
```

3 ERROR.

- [ ] **Step 6.3 : Impl**

Créer `backend/src/rag/indexer/providers/ollama.py` :

```python
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

_TIMEOUT_SECONDS = 60.0  # LLMs locaux peuvent être lents
_DEFAULT_RETRY_SLEEP_SECONDS = 5.0


class OllamaProvider:
    """Implémentation `EmbeddingProvider` pour Ollama (LXC homelab).

    Endpoint : `POST <base_url>/api/embeddings`.
    Pas d'auth (LXC local). 1 texte par call (l'API Ollama est mono-input).
    Boucle séquentielle pour préserver l'ordre — Ollama mono-thread CPU.
    """

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        transport: httpx.BaseTransport | None = None,
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
            transport=self._transport, timeout=_TIMEOUT_SECONDS,
        ) as client:
            for text in texts:
                results.append(await self._embed_one(client, text))
        return results

    async def _embed_one(
        self, client: httpx.AsyncClient, text: str,
    ) -> list[float]:
        for attempt in (0, 1):
            try:
                response = await client.post(
                    f"{self._base_url}/api/embeddings",
                    json={"model": self._model, "prompt": text},
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
                embedding = payload.get("embedding")
                if not isinstance(embedding, list):
                    raise EmbeddingProviderError(
                        "Ollama response missing 'embedding' field"
                    )
                return embedding

            if response.status_code in (503,):
                if attempt == 0:
                    log.warning(
                        "ollama.embed.transient_retry", status=response.status_code,
                    )
                    await asyncio.sleep(self._retry_sleep)
                    continue
                raise EmbeddingProviderUnreachable("Ollama 503 (after retry)")

            raise EmbeddingProviderUnreachable(
                f"Ollama unexpected status: HTTP {response.status_code}"
            )

        raise EmbeddingProviderUnreachable("Ollama: retry loop exited unexpectedly")
```

- [ ] **Step 6.4 : Vert + lint + commit**

```powershell
uv run pytest tests/unit/test_provider_ollama.py -v
uv run ruff check src/rag/indexer/providers/ollama.py tests/unit/test_provider_ollama.py
uv run mypy src/rag/indexer/providers/ollama.py
```

3 PASS + clean.

```bash
git add backend/src/rag/indexer/providers/ollama.py backend/tests/unit/test_provider_ollama.py
git commit -m "feat(indexer/providers): OllamaProvider (mono-input séquentiel, base_url configurable)"
```

---

## Task 7 — `providers/factory.py` : `make_provider`

**Files:**
- Create: `backend/src/rag/indexer/providers/factory.py`
- Create: `backend/tests/unit/test_provider_factory.py`

- [ ] **Step 7.1 : Tests (rouge)**

Créer `backend/tests/unit/test_provider_factory.py` :

```python
from __future__ import annotations

import pytest

from rag.indexer.providers.factory import make_provider
from rag.indexer.providers.ollama import OllamaProvider
from rag.indexer.providers.openai import OpenAIProvider
from rag.indexer.providers.voyage import VoyageProvider


def test_make_provider_openai_returns_openai_instance() -> None:
    p = make_provider(
        provider="openai", model="text-embedding-3-small",
        api_key="sk-x", base_url=None,
    )
    assert isinstance(p, OpenAIProvider)


def test_make_provider_voyage_returns_voyage_instance() -> None:
    p = make_provider(
        provider="voyage", model="voyage-3", api_key="vk-x", base_url=None,
    )
    assert isinstance(p, VoyageProvider)


def test_make_provider_ollama_uses_default_base_url() -> None:
    p = make_provider(
        provider="ollama", model="nomic-embed-text",
        api_key=None, base_url=None,
    )
    assert isinstance(p, OllamaProvider)


def test_make_provider_ollama_uses_explicit_base_url() -> None:
    p = make_provider(
        provider="ollama", model="nomic-embed-text",
        api_key=None, base_url="http://custom-ollama:11434",
    )
    assert isinstance(p, OllamaProvider)


def test_make_provider_unknown_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unsupported provider"):
        make_provider(
            provider="cohere", model="x", api_key=None, base_url=None,
        )
```

- [ ] **Step 7.2 : Lancer (rouge)**

```powershell
uv run pytest tests/unit/test_provider_factory.py -v
```

5 ERROR.

- [ ] **Step 7.3 : Impl**

Créer `backend/src/rag/indexer/providers/factory.py` :

```python
from __future__ import annotations

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

    - `openai` / `voyage` : `api_key` requis (lève EmbeddingAuthError au
      premier `embed_texts` si None).
    - `ollama` : `api_key` ignoré ; `base_url` fallback sur pve2 homelab.
    - Provider inconnu : `ValueError`.
    """
    if provider == "openai":
        return OpenAIProvider(model=model, api_key=api_key)
    if provider == "voyage":
        return VoyageProvider(model=model, api_key=api_key)
    if provider == "ollama":
        return OllamaProvider(
            model=model, base_url=base_url or _OLLAMA_DEFAULT_BASE_URL,
        )
    raise ValueError(f"Unsupported provider: {provider!r}")
```

- [ ] **Step 7.4 : Vert + lint + commit**

```powershell
uv run pytest tests/unit/test_provider_factory.py -v
uv run ruff check src/rag/indexer/providers/factory.py tests/unit/test_provider_factory.py
uv run mypy src/rag/indexer/providers/factory.py
```

5 PASS + clean.

```bash
git add backend/src/rag/indexer/providers/factory.py backend/tests/unit/test_provider_factory.py
git commit -m "feat(indexer/providers): factory.make_provider (dispatch openai/voyage/ollama)"
```

---

## Task 8 — `db/workspace_embeddings.py` : upsert + delete pgvector

**Files:**
- Create: `backend/src/rag/db/workspace_embeddings.py`
- Create: `backend/tests/integration/test_workspace_embeddings.py`

Cette task crée une fixture pgvector pour les tests : un workspace de test avec `vector` extension + table `embeddings(vector(N))`. Les tests roulent sur le Postgres LXC (déjà en place via `pg_container`) en créant des bases jetables avec pgvector activé.

- [ ] **Step 8.1 : Tests (rouge)**

Créer `backend/tests/integration/test_workspace_embeddings.py` :

```python
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio
from pgvector.asyncpg import register_vector

from rag.db.workspace_embeddings import (
    delete_chunks_for_path,
    delete_path,
    upsert_chunks,
)


@pytest_asyncio.fixture
async def ws_pool_with_embeddings(
    pg_container: str,
) -> AsyncIterator[asyncpg.Pool]:
    """Crée une base workspace test (pgvector + table embeddings) et yield un pool."""
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    dbname = f"rag_test_emb_{uuid.uuid4().hex[:10]}"

    # CREATE DATABASE via admin
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        await admin.close()

    ws_dsn = pg_container.rsplit("/", 1)[0] + f"/{dbname}"

    # Setup schema dans la nouvelle DB
    setup = await asyncpg.connect(ws_dsn)
    try:
        await setup.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await setup.execute(
            """
            CREATE TABLE embeddings (
                id           SERIAL PRIMARY KEY,
                path         TEXT NOT NULL,
                chunk_index  INT  NOT NULL,
                content      TEXT NOT NULL,
                embedding    vector(4) NOT NULL,
                indexed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (path, chunk_index)
            )
            """
        )
    finally:
        await setup.close()

    # Pool avec pgvector enregistré sur chaque connexion
    pool = await asyncpg.create_pool(
        ws_dsn,
        min_size=1,
        max_size=4,
        init=register_vector,
    )

    try:
        yield pool
    finally:
        await pool.close()
        # Drop la DB de test
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        finally:
            await admin.close()


@pytest.mark.asyncio
async def test_upsert_chunks_inserts_n_rows(
    ws_pool_with_embeddings: asyncpg.Pool,
) -> None:
    count = await upsert_chunks(
        ws_pool_with_embeddings,
        path="docs/a.md",
        chunks=["chunk 1", "chunk 2", "chunk 3"],
        embeddings=[[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]],
    )
    assert count == 3
    rows = await ws_pool_with_embeddings.fetch(
        "SELECT path, chunk_index, content FROM embeddings ORDER BY chunk_index"
    )
    assert len(rows) == 3
    assert [r["chunk_index"] for r in rows] == [0, 1, 2]
    assert rows[0]["content"] == "chunk 1"


@pytest.mark.asyncio
async def test_upsert_chunks_replaces_existing_for_same_path(
    ws_pool_with_embeddings: asyncpg.Pool,
) -> None:
    await upsert_chunks(
        ws_pool_with_embeddings, path="a.md",
        chunks=["v1-c0", "v1-c1", "v1-c2"],
        embeddings=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]],
    )
    # Upsert v2 avec MOINS de chunks
    await upsert_chunks(
        ws_pool_with_embeddings, path="a.md",
        chunks=["v2-c0", "v2-c1"],
        embeddings=[[0, 1, 0, 0], [0, 0, 1, 0]],
    )
    rows = await ws_pool_with_embeddings.fetch(
        "SELECT chunk_index, content FROM embeddings WHERE path='a.md' "
        "ORDER BY chunk_index"
    )
    assert len(rows) == 2
    assert [r["content"] for r in rows] == ["v2-c0", "v2-c1"]


@pytest.mark.asyncio
async def test_upsert_chunks_other_paths_untouched(
    ws_pool_with_embeddings: asyncpg.Pool,
) -> None:
    await upsert_chunks(
        ws_pool_with_embeddings, path="a.md",
        chunks=["a-c0"], embeddings=[[1, 0, 0, 0]],
    )
    await upsert_chunks(
        ws_pool_with_embeddings, path="b.md",
        chunks=["b-c0"], embeddings=[[0, 1, 0, 0]],
    )
    # Upsert sur a.md ne doit pas toucher b.md
    await upsert_chunks(
        ws_pool_with_embeddings, path="a.md",
        chunks=["a-c0-new"], embeddings=[[0, 0, 1, 0]],
    )
    b_content = await ws_pool_with_embeddings.fetchval(
        "SELECT content FROM embeddings WHERE path='b.md'"
    )
    assert b_content == "b-c0"


@pytest.mark.asyncio
async def test_upsert_chunks_mismatched_lengths_raises(
    ws_pool_with_embeddings: asyncpg.Pool,
) -> None:
    with pytest.raises(ValueError, match="chunks.*embeddings"):
        await upsert_chunks(
            ws_pool_with_embeddings, path="a.md",
            chunks=["c0", "c1"], embeddings=[[1, 0, 0, 0]],
        )


@pytest.mark.asyncio
async def test_delete_chunks_for_path_removes_all_chunks(
    ws_pool_with_embeddings: asyncpg.Pool,
) -> None:
    await upsert_chunks(
        ws_pool_with_embeddings, path="a.md",
        chunks=["c0", "c1"], embeddings=[[1, 0, 0, 0], [0, 1, 0, 0]],
    )
    deleted = await delete_chunks_for_path(ws_pool_with_embeddings, "a.md")
    assert deleted == 2
    rows = await ws_pool_with_embeddings.fetch(
        "SELECT 1 FROM embeddings WHERE path='a.md'"
    )
    assert rows == []


@pytest.mark.asyncio
async def test_delete_chunks_for_absent_path_returns_zero(
    ws_pool_with_embeddings: asyncpg.Pool,
) -> None:
    deleted = await delete_chunks_for_path(ws_pool_with_embeddings, "ghost.md")
    assert deleted == 0


@pytest.mark.asyncio
async def test_delete_path_alias_works(
    ws_pool_with_embeddings: asyncpg.Pool,
) -> None:
    """delete_path est l'alias sémantique consommé par RealIndexer.delete_file."""
    await upsert_chunks(
        ws_pool_with_embeddings, path="a.md",
        chunks=["c"], embeddings=[[1, 0, 0, 0]],
    )
    await delete_path(ws_pool_with_embeddings, "a.md")
    rows = await ws_pool_with_embeddings.fetch("SELECT 1 FROM embeddings")
    assert rows == []
```

- [ ] **Step 8.2 : Lancer (rouge)**

```powershell
$env:TEST_POSTGRES_PASSWORD = "i22BfVjVnEG1FhKL0sJ1CuznH73twl1J"
uv run pytest tests/integration/test_workspace_embeddings.py -v
```

7 ERROR `ModuleNotFoundError`.

- [ ] **Step 8.3 : Impl**

Créer `backend/src/rag/db/workspace_embeddings.py` :

```python
from __future__ import annotations

import asyncpg
import structlog
from pgvector.asyncpg import register_vector

log = structlog.get_logger(__name__)


async def upsert_chunks(
    workspace_pool: asyncpg.Pool,
    *,
    path: str,
    chunks: list[str],
    embeddings: list[list[float]],
) -> int:
    """Remplace tous les chunks d'un path par une nouvelle liste.

    Stratégie : DELETE FROM embeddings WHERE path=$1 puis INSERT batch,
    dans une transaction unique pour l'atomicité.

    Pré-condition : `len(chunks) == len(embeddings)` — sinon ValueError.
    Retourne le nombre de chunks insérés.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) "
            "must have the same length"
        )
    if not chunks:
        # Cas dégénéré : juste supprimer ce qui existait pour ce path.
        return await delete_chunks_for_path(workspace_pool, path) and 0

    async with workspace_pool.acquire() as conn, conn.transaction():
        # pgvector enregistre les codecs vector sur la connexion ; si le pool
        # n'a pas été créé avec init=register_vector, on le fait ici.
        await register_vector(conn)
        await conn.execute(
            "DELETE FROM embeddings WHERE path=$1", path,
        )
        records = [
            (path, idx, content, embedding)
            for idx, (content, embedding) in enumerate(zip(chunks, embeddings, strict=True))
        ]
        await conn.executemany(
            "INSERT INTO embeddings (path, chunk_index, content, embedding) "
            "VALUES ($1, $2, $3, $4)",
            records,
        )

    log.info(
        "workspace_embeddings.upserted",
        path=path, chunks=len(chunks),
    )
    return len(chunks)


async def delete_chunks_for_path(
    workspace_pool: asyncpg.Pool, path: str,
) -> int:
    """DELETE FROM embeddings WHERE path=$1. Retourne nombre supprimé."""
    async with workspace_pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM embeddings WHERE path=$1", path,
        )
    count = int(result.split()[-1])
    if count > 0:
        log.info(
            "workspace_embeddings.deleted",
            path=path, count=count,
        )
    return count


async def delete_path(workspace_pool: asyncpg.Pool, path: str) -> None:
    """Alias sémantique de delete_chunks_for_path utilisé par RealIndexer."""
    await delete_chunks_for_path(workspace_pool, path)
```

- [ ] **Step 8.4 : Vert + lint + commit**

```powershell
uv run pytest tests/integration/test_workspace_embeddings.py -v
uv run ruff check src/rag/db/workspace_embeddings.py tests/integration/test_workspace_embeddings.py
uv run mypy src/rag/db/workspace_embeddings.py
```

7 PASS + clean.

```bash
git add backend/src/rag/db/workspace_embeddings.py backend/tests/integration/test_workspace_embeddings.py
git commit -m "feat(db): workspace_embeddings (upsert DELETE+INSERT batch via pgvector)"
```

---

## Task 9 — `indexer/real.py` : `RealIndexer`

**Files:**
- Create: `backend/src/rag/indexer/real.py`
- Create: `backend/tests/integration/test_indexer_real.py`

C'est la task qui orchestre tout. Tests E2E avec provider mocké (pas d'appel HTTP réel) mais avec vraies bases workspace pgvector + indexed_documents.

- [ ] **Step 9.1 : Tests (rouge)**

Créer `backend/tests/integration/test_indexer_real.py` :

```python
from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import asyncpg
import pytest
import pytest_asyncio
from pgvector.asyncpg import register_vector

from rag.db.migrations import run_migrations
from rag.db.pool import WorkspacePoolRegistry
from rag.indexer.providers.protocol import (
    EmbeddingAuthError,
    EmbeddingProvider,
)
from rag.indexer.real import RealIndexer

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _StubProvider:
    """Provider mocké : retourne des vecteurs déterministes (dim 4)."""

    def __init__(self, *, raise_on_call: Exception | None = None) -> None:
        self._raise = raise_on_call
        self.calls: list[list[str]] = []

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self._raise is not None:
            raise self._raise
        self.calls.append(texts)
        return [[float(i + 1), 0.0, 0.0, 0.0] for i in range(len(texts))]


class _StubResolver:
    def resolve_with_retry(self, ref: str) -> str:
        return "tok-stub"


@pytest_asyncio.fixture
async def real_indexer_setup(
    pg_container: str, session_pool: asyncpg.Pool,
) -> AsyncIterator[dict[str, Any]]:
    """Provisionne :
      - migrations 001-007 sur la base config
      - 1 workspace 'ws_real_a' avec provider 'openai' / model 'text-embedding-3-small'
      - 1 base workspace `rag_test_emb_<uuid>` avec table embeddings (dim 4 pour les tests)
      - WorkspacePoolRegistry initialisé
      - StubProvider injecté via provider_factory custom
    """
    await run_migrations(session_pool, MIGRATIONS_DIR)

    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"

    # Crée la base workspace test
    ws_dbname = f"rag_test_emb_{uuid.uuid4().hex[:10]}"
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{ws_dbname}"')
    finally:
        await admin.close()
    ws_dsn = pg_container.rsplit("/", 1)[0] + f"/{ws_dbname}"
    ws_setup = await asyncpg.connect(ws_dsn)
    try:
        await ws_setup.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await ws_setup.execute(
            """
            CREATE TABLE embeddings (
                id SERIAL PRIMARY KEY,
                path TEXT NOT NULL,
                chunk_index INT NOT NULL,
                content TEXT NOT NULL,
                embedding vector(4) NOT NULL,
                indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (path, chunk_index)
            )
            """
        )
    finally:
        await ws_setup.close()

    # Crée le workspace en config DB
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ($1, 'h', $2, $3) RETURNING id",
            "ws_real_a", ws_dsn, ws_dbname,
        )
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, api_key_ref, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 'openai_key', 4)",
            ws_id,
        )

    # Registry pour les pools workspace
    registry = WorkspacePoolRegistry(
        config_dsn=pg_container, admin_dsn=admin_dsn,
    )
    await registry.start()

    yield {
        "workspace_id": ws_id,
        "workspace_name": "ws_real_a",
        "ws_dsn": ws_dsn,
        "ws_dbname": ws_dbname,
        "registry": registry,
    }

    await registry.close_all()

    # Cleanup base workspace
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{ws_dbname}" WITH (FORCE)')
    finally:
        await admin.close()


def _factory_with_stub(stub: _StubProvider) -> Any:
    def _factory(**_kwargs: Any) -> EmbeddingProvider:
        return stub
    return _factory


@pytest.mark.asyncio
async def test_real_indexer_index_file_inserts_chunks_and_indexed_documents(
    session_pool: asyncpg.Pool, real_indexer_setup: dict[str, Any],
) -> None:
    setup = real_indexer_setup
    stub = _StubProvider()
    indexer = RealIndexer(
        config_pool=session_pool,
        pool_registry=setup["registry"],
        secret_resolver=_StubResolver(),  # type: ignore[arg-type]
        provider_factory=_factory_with_stub(stub),
    )

    chunks_count = await indexer.index_file(
        workspace_id=setup["workspace_id"],
        path="docs/a.md",
        content="Hello world.\n\nSecond paragraph.",
        content_hash="sha256:abc",
        indexer_used="openai/text-embedding-3-small",
    )

    assert chunks_count >= 1
    assert len(stub.calls) == 1  # 1 batch d'embeddings

    # Vérifie indexed_documents
    row = await session_pool.fetchrow(
        "SELECT content_hash, indexer_used FROM indexed_documents "
        "WHERE workspace_id=$1 AND path='docs/a.md'",
        setup["workspace_id"],
    )
    assert row is not None
    assert row["content_hash"] == "sha256:abc"

    # Vérifie embeddings dans rag_test_emb_<uuid>
    ws_pool = await setup["registry"].get_workspace_pool(
        setup["workspace_name"], setup["ws_dsn"],
    )
    chunks_in_db = await ws_pool.fetch(
        "SELECT chunk_index FROM embeddings WHERE path='docs/a.md' "
        "ORDER BY chunk_index"
    )
    assert len(chunks_in_db) == chunks_count


@pytest.mark.asyncio
async def test_real_indexer_index_file_replaces_old_chunks(
    session_pool: asyncpg.Pool, real_indexer_setup: dict[str, Any],
) -> None:
    setup = real_indexer_setup
    indexer = RealIndexer(
        config_pool=session_pool,
        pool_registry=setup["registry"],
        secret_resolver=_StubResolver(),  # type: ignore[arg-type]
        provider_factory=_factory_with_stub(_StubProvider()),
    )
    # Index v1
    await indexer.index_file(
        workspace_id=setup["workspace_id"], path="docs/a.md",
        content="v1 content here.", content_hash="h1",
        indexer_used="openai/text-embedding-3-small",
    )
    # Index v2 (contenu différent → nouvelle indexation)
    await indexer.index_file(
        workspace_id=setup["workspace_id"], path="docs/a.md",
        content="v2 brand new content.", content_hash="h2",
        indexer_used="openai/text-embedding-3-small",
    )

    # Le hash en base reflète v2
    h = await session_pool.fetchval(
        "SELECT content_hash FROM indexed_documents WHERE path='docs/a.md'",
    )
    assert h == "h2"


@pytest.mark.asyncio
async def test_real_indexer_index_file_empty_content_returns_zero(
    session_pool: asyncpg.Pool, real_indexer_setup: dict[str, Any],
) -> None:
    setup = real_indexer_setup
    stub = _StubProvider()
    indexer = RealIndexer(
        config_pool=session_pool,
        pool_registry=setup["registry"],
        secret_resolver=_StubResolver(),  # type: ignore[arg-type]
        provider_factory=_factory_with_stub(stub),
    )
    n = await indexer.index_file(
        workspace_id=setup["workspace_id"], path="empty.md",
        content="", content_hash="h0",
        indexer_used="openai/text-embedding-3-small",
    )
    assert n == 0
    assert stub.calls == []  # pas d'appel provider

    # indexed_documents : pas de ligne (rien à indexer)
    row = await session_pool.fetchrow(
        "SELECT 1 FROM indexed_documents WHERE path='empty.md'",
    )
    assert row is None


@pytest.mark.asyncio
async def test_real_indexer_delete_file_removes_chunks_and_metadata(
    session_pool: asyncpg.Pool, real_indexer_setup: dict[str, Any],
) -> None:
    setup = real_indexer_setup
    indexer = RealIndexer(
        config_pool=session_pool,
        pool_registry=setup["registry"],
        secret_resolver=_StubResolver(),  # type: ignore[arg-type]
        provider_factory=_factory_with_stub(_StubProvider()),
    )
    await indexer.index_file(
        workspace_id=setup["workspace_id"], path="docs/b.md",
        content="some content", content_hash="h",
        indexer_used="openai/text-embedding-3-small",
    )
    await indexer.delete_file(
        workspace_id=setup["workspace_id"], path="docs/b.md",
    )

    # indexed_documents : ligne supprimée
    row = await session_pool.fetchrow(
        "SELECT 1 FROM indexed_documents WHERE path='docs/b.md'",
    )
    assert row is None

    # embeddings : aussi supprimés
    ws_pool = await setup["registry"].get_workspace_pool(
        setup["workspace_name"], setup["ws_dsn"],
    )
    rows = await ws_pool.fetch(
        "SELECT 1 FROM embeddings WHERE path='docs/b.md'",
    )
    assert rows == []


@pytest.mark.asyncio
async def test_real_indexer_provider_auth_error_propagates(
    session_pool: asyncpg.Pool, real_indexer_setup: dict[str, Any],
) -> None:
    setup = real_indexer_setup
    bad_stub = _StubProvider(raise_on_call=EmbeddingAuthError("401"))
    indexer = RealIndexer(
        config_pool=session_pool,
        pool_registry=setup["registry"],
        secret_resolver=_StubResolver(),  # type: ignore[arg-type]
        provider_factory=_factory_with_stub(bad_stub),
    )
    with pytest.raises(EmbeddingAuthError):
        await indexer.index_file(
            workspace_id=setup["workspace_id"], path="docs/x.md",
            content="hello", content_hash="h",
            indexer_used="openai/text-embedding-3-small",
        )
```

- [ ] **Step 9.2 : Lancer (rouge)**

```powershell
uv run pytest tests/integration/test_indexer_real.py -v
```

5 ERROR `cannot import 'RealIndexer'`.

- [ ] **Step 9.3 : Impl**

Créer `backend/src/rag/indexer/real.py` :

```python
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol
from uuid import UUID

import asyncpg
import structlog

from rag.db.pool import WorkspacePoolRegistry
from rag.db.workspace_embeddings import delete_path, upsert_chunks
from rag.indexer.chunking import chunk_text
from rag.indexer.providers.factory import make_provider
from rag.indexer.providers.protocol import EmbeddingProvider

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    def resolve_with_retry(self, ref: str) -> str: ...


def _to_vault_ref(logical_key: str, *, vault_id: str = "rag") -> str:
    return f"${{vault://{vault_id}:{logical_key}}}"


class RealIndexer:
    """Implémentation effective de `IndexerProtocol` (M4a).

    Pipeline `index_file` :
      1. Charge le contexte workspace (provider, model, api_key_ref, base_url, rag_cnx).
      2. Chunke le contenu (`chunking.chunk_text`).
      3. Résout l'API key via SecretResolver (lazy, juste avant l'embed).
      4. Embed les chunks via le provider configuré.
      5. Upsert pgvector dans `rag_<workspace>.embeddings` (transaction).
      6. UPDATE `indexed_documents` (config_pool) — hash, indexer_used.

    `delete_file` :
      1. Charge le contexte workspace (pour le pool).
      2. DELETE FROM embeddings WHERE path=$1.
      3. DELETE FROM indexed_documents WHERE workspace_id=$1 AND path=$2.
    """

    def __init__(
        self,
        *,
        config_pool: asyncpg.Pool,
        pool_registry: WorkspacePoolRegistry,
        secret_resolver: _ResolverProtocol,
        provider_factory: Callable[..., EmbeddingProvider] = make_provider,
    ) -> None:
        self._config_pool = config_pool
        self._pool_registry = pool_registry
        self._secret_resolver = secret_resolver
        self._provider_factory = provider_factory

    async def index_file(
        self,
        *,
        workspace_id: UUID,
        path: str,
        content: str,
        content_hash: str,
        indexer_used: str,
    ) -> int:
        ctx = await self._load_workspace_context(workspace_id)

        chunks = chunk_text(content)
        if not chunks:
            log.info("real_indexer.empty_content_skipped", path=path)
            return 0

        api_key: str | None = None
        if ctx["api_key_ref"]:
            api_key = self._secret_resolver.resolve_with_retry(
                _to_vault_ref(ctx["api_key_ref"]),
            )

        provider = self._provider_factory(
            provider=ctx["provider"],
            model=ctx["model"],
            api_key=api_key,
            base_url=ctx["base_url"],
        )
        embeddings = await provider.embed_texts(chunks)

        ws_pool = await self._pool_registry.get_workspace_pool(
            ctx["workspace_name"], ctx["rag_cnx"],
        )
        await upsert_chunks(
            ws_pool, path=path, chunks=chunks, embeddings=embeddings,
        )

        async with self._config_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO indexed_documents
                    (workspace_id, path, content_hash, indexer_used, indexed_at)
                VALUES ($1, $2, $3, $4, now())
                ON CONFLICT (workspace_id, path) DO UPDATE
                SET content_hash=EXCLUDED.content_hash,
                    indexer_used=EXCLUDED.indexer_used,
                    indexed_at=EXCLUDED.indexed_at
                """,
                workspace_id, path, content_hash, indexer_used,
            )

        log.info(
            "real_indexer.indexed",
            workspace_id=str(workspace_id), path=path,
            chunks=len(chunks),
        )
        return len(chunks)

    async def delete_file(self, *, workspace_id: UUID, path: str) -> None:
        ctx = await self._load_workspace_context(workspace_id)
        ws_pool = await self._pool_registry.get_workspace_pool(
            ctx["workspace_name"], ctx["rag_cnx"],
        )
        await delete_path(ws_pool, path)
        async with self._config_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM indexed_documents WHERE workspace_id=$1 AND path=$2",
                workspace_id, path,
            )
        log.info(
            "real_indexer.deleted",
            workspace_id=str(workspace_id), path=path,
        )

    async def _load_workspace_context(
        self, workspace_id: UUID,
    ) -> dict[str, Any]:
        row = await self._config_pool.fetchrow(
            """
            SELECT
                w.name AS workspace_name,
                w.rag_cnx AS rag_cnx,
                ic.provider AS provider,
                ic.model AS model,
                ic.api_key_ref AS api_key_ref,
                ic.base_url AS base_url
            FROM workspaces w
            JOIN indexer_configs ic ON ic.workspace_id = w.id
            WHERE w.id = $1
            """,
            workspace_id,
        )
        if row is None:
            raise RuntimeError(
                f"Workspace {workspace_id} or its indexer_config not found"
            )
        return dict(row)
```

- [ ] **Step 9.4 : Vert + lint + commit**

```powershell
uv run pytest tests/integration/test_indexer_real.py -v
uv run ruff check src/rag/indexer/real.py tests/integration/test_indexer_real.py
uv run mypy src/rag/indexer/real.py
```

5 PASS + clean.

```bash
git add backend/src/rag/indexer/real.py backend/tests/integration/test_indexer_real.py
git commit -m "feat(indexer): RealIndexer (chunking + provider + upsert pgvector + indexed_documents)"
```

NE PAS pusher.

---

## Task 10 — `main.py` : wire-up `RealIndexer` (remplace `NoOpIndexer`)

**Files:**
- Modify: `backend/src/rag/main.py`
- Modify: `backend/tests/api/test_sync_wireup.py` (ajout d'1 assert)

- [ ] **Step 10.1 : Étendre le test wire-up**

Dans `backend/tests/api/test_sync_wireup.py`, ajouter en fin :

```python
def test_sync_worker_uses_real_indexer_not_noop(wired_client: TestClient) -> None:
    """Après M4a : l'indexer injecté au SyncWorker doit être RealIndexer."""
    from rag.indexer.real import RealIndexer

    app = wired_client.app
    worker = app.state.sync_worker
    # On accède au `_indexer` privé du worker — pas idéal mais nécessaire
    # pour valider l'injection sans exposer l'attribut publiquement.
    assert isinstance(worker._indexer, RealIndexer), (
        f"Expected RealIndexer, got {type(worker._indexer).__name__}"
    )
```

- [ ] **Step 10.2 : Lancer (rouge)**

```powershell
$env:TEST_POSTGRES_PASSWORD = "i22BfVjVnEG1FhKL0sJ1CuznH73twl1J"
uv run pytest tests/api/test_sync_wireup.py::test_sync_worker_uses_real_indexer_not_noop -v
```

FAIL : `Expected RealIndexer, got NoOpIndexer`.

- [ ] **Step 10.3 : Modifier `main.py`**

Dans `backend/src/rag/main.py`, fonction `build_app`, dans le `lifespan`, **remplacer** le bloc d'instanciation `SyncWorker` actuel :

```python
        # AVANT (M3) :
        from rag.indexer.noop import NoOpIndexer
        from rag.sync.repo_storage import RepoStorage
        from rag.sync.worker import SyncWorker

        sync_worker = SyncWorker(
            config_pool=registry.config_pool,
            storage=RepoStorage(root=settings.sync_repos_root),
            indexer=NoOpIndexer(registry.config_pool),
            resolver=app.state.resolver,
            poll_interval_seconds=settings.sync_worker_poll_interval_seconds,
            default_sync_interval_seconds=settings.sync_default_interval_seconds,
        )
```

par :

```python
        # APRÈS (M4a) : RealIndexer remplace NoOpIndexer
        from rag.indexer.real import RealIndexer
        from rag.sync.repo_storage import RepoStorage
        from rag.sync.worker import SyncWorker

        sync_worker = SyncWorker(
            config_pool=registry.config_pool,
            storage=RepoStorage(root=settings.sync_repos_root),
            indexer=RealIndexer(
                config_pool=registry.config_pool,
                pool_registry=registry,
                secret_resolver=app.state.resolver,
            ),
            resolver=app.state.resolver,
            poll_interval_seconds=settings.sync_worker_poll_interval_seconds,
            default_sync_interval_seconds=settings.sync_default_interval_seconds,
        )
```

Note : `NoOpIndexer` reste importable (`rag.indexer.noop`) pour les tests qui en ont besoin (tests `SyncWorker` qui n'ont pas besoin d'embedder vraiment). Pas de suppression.

- [ ] **Step 10.4 : Vert + régression**

```powershell
uv run pytest tests/api/test_sync_wireup.py -v
```

3 PASS (les 2 anciens M3 + le nouveau).

Run aussi tous les tests M3 pour valider l'absence de régression (l'E2E sync utilise désormais RealIndexer, donc il faut le provider stub via OS env… ou utiliser un test qui injecte NoOpIndexer explicitement).

```powershell
uv run pytest tests/api/test_sync_e2e.py -v
```

Si le test M3 `test_full_pipeline_create_workspace_source_reindex_done` échoue à cause de `RealIndexer` qui appelle vraiment OpenAI : c'est attendu. Le test M3 utilise `_AcceptAllResolver` mais le RealIndexer va appeler le provider OpenAI HTTP. Solution : modifier ce test pour injecter un stub provider via env var ou refactor.

**Action si échec** : modifier `tests/api/test_sync_e2e.py` pour utiliser un `resolver_factory` qui retourne un resolver dont les refs Harpocrate fonctionnent ET un `provider_factory` stub. Le plus simple : ajouter un paramètre à `build_app` pour injecter un `indexer_factory` (pas seulement un resolver) — mais c'est un changement d'API. Alternative : marquer ce test E2E comme `@pytest.mark.smoke` (skippé par défaut) car il dépend désormais d'un vrai provider.

**Décision pragmatique** : marquer le test E2E M3 `@pytest.mark.smoke` (skippé en CI). Le test wireup T10 valide que `RealIndexer` est branché ; un nouveau test E2E avec injection sera ajouté en T11 si besoin.

Pour ce step : si `test_sync_e2e.py` échoue post-M4a, ajouter `@pytest.mark.smoke` au-dessus du test :

```python
@pytest.mark.smoke
def test_full_pipeline_create_workspace_source_reindex_done(...):
    ...
```

- [ ] **Step 10.5 : Lint + commit**

```powershell
uv run ruff check src/rag/main.py tests/api/test_sync_wireup.py
uv run ruff format --check src/rag/main.py tests/api/test_sync_wireup.py
uv run mypy src/rag/main.py
```

Clean.

```bash
git add backend/src/rag/main.py backend/tests/api/test_sync_wireup.py backend/tests/api/test_sync_e2e.py
git commit -m "feat(main): RealIndexer remplace NoOpIndexer au lifespan"
```

NE PAS pusher.

---

## Task 11 — Tests smoke opt-in providers + README

**Files:**
- Create: `backend/tests/smoke/__init__.py` (vide)
- Create: `backend/tests/smoke/test_providers_smoke.py`
- Modify: `backend/README.md`

- [ ] **Step 11.1 : Créer le dossier smoke + __init__**

```powershell
New-Item -ItemType Directory -Path "E:\srcs\ag-flow.rag\backend\tests\smoke" -Force
```

Créer `backend/tests/smoke/__init__.py` (vide).

- [ ] **Step 11.2 : Tests smoke**

Créer `backend/tests/smoke/test_providers_smoke.py` :

```python
"""Tests smoke opt-in pour les 3 providers réels.

Skippés par défaut. Pour les exécuter :

    $env:OPENAI_API_KEY_TEST = "sk-..."
    $env:VOYAGE_API_KEY_TEST = "vk-..."
    $env:OLLAMA_TEST_URL     = "http://192.168.10.80:11434"
    uv run pytest -m smoke -v

Chaque test skip individuellement si sa variable d'env n'est pas définie.
"""
from __future__ import annotations

import os

import pytest

from rag.indexer.providers.ollama import OllamaProvider
from rag.indexer.providers.openai import OpenAIProvider
from rag.indexer.providers.voyage import VoyageProvider


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_openai_real_returns_1536_dim() -> None:
    api_key = os.environ.get("OPENAI_API_KEY_TEST")
    if not api_key:
        pytest.skip("OPENAI_API_KEY_TEST not set")
    provider = OpenAIProvider(model="text-embedding-3-small", api_key=api_key)
    result = await provider.embed_texts(["hello", "world"])
    assert len(result) == 2
    assert len(result[0]) == 1536


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_voyage_real_returns_1024_dim() -> None:
    api_key = os.environ.get("VOYAGE_API_KEY_TEST")
    if not api_key:
        pytest.skip("VOYAGE_API_KEY_TEST not set")
    provider = VoyageProvider(model="voyage-3", api_key=api_key)
    result = await provider.embed_texts(["hello"])
    assert len(result) == 1
    assert len(result[0]) == 1024


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_ollama_real_returns_dim() -> None:
    base_url = os.environ.get("OLLAMA_TEST_URL")
    if not base_url:
        pytest.skip("OLLAMA_TEST_URL not set")
    provider = OllamaProvider(model="nomic-embed-text", base_url=base_url)
    result = await provider.embed_texts(["hello"])
    assert len(result) == 1
    assert len(result[0]) == 768
```

- [ ] **Step 11.3 : Vérifier que les smoke sont skippés par défaut**

```powershell
uv run pytest tests/smoke/ -v
```

Attendu : 3 SKIPPED (les env vars ne sont pas définies).

```powershell
uv run pytest tests/smoke/ -v -m smoke
```

Attendu : 3 SKIPPED (idem — la deselection inversée ferait passer, mais skip individuel reste).

- [ ] **Step 11.4 : Étendre `backend/README.md`**

Dans la section "Tests" de `backend/README.md`, ajouter (après la liste des cibles existantes) :

````markdown
### Smoke opt-in (providers réels)

Les tests smoke valident les providers d'embedding contre les vraies APIs.
Ils sont **skippés par défaut**. Pour les exécuter, définir les env vars
correspondantes :

```powershell
$env:OPENAI_API_KEY_TEST = "sk-..."           # OpenAI test key (créer un compte dédié)
$env:VOYAGE_API_KEY_TEST = "vk-..."           # Voyage AI test key
$env:OLLAMA_TEST_URL     = "http://192.168.10.80:11434"   # LXC Ollama homelab
uv run pytest -m smoke -v
```

Chaque test skip individuellement si sa variable d'env n'est pas définie.
Coût estimé OpenAI : <$0.001 par run (text-embedding-3-small).
````

- [ ] **Step 11.5 : Lint + commit**

```powershell
uv run ruff check tests/smoke/
uv run ruff format --check tests/smoke/
```

Clean.

```bash
git add backend/tests/smoke/ backend/README.md
git commit -m "test(smoke): providers réels OpenAI/Voyage/Ollama opt-in + doc README"
```

NE PAS pusher.

---

## Task 12 — Quality gate + smoke deploy LXC + tag m4a-done

**Files:**
- aucun nouveau

- [ ] **Step 12.1 : Quality gate local complet**

```powershell
$env:TEST_POSTGRES_PASSWORD = "i22BfVjVnEG1FhKL0sJ1CuznH73twl1J"
Set-Location E:\srcs\ag-flow.rag\backend
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src/rag
uv run pytest --cov=src/rag --cov-report=term-missing
```

Attendu :
- ruff / format / mypy : 0 issue
- pytest : ~270+ tests verts (238 M3 + ~35 M4a)
- couverture : ≥90% globale, ≥95% sur `indexer/chunking.py`, `indexer/real.py`, `indexer/providers/*`, `db/workspace_embeddings.py`

Si fail → fix (commit `chore: corrections quality gate M4a`).

- [ ] **Step 12.2 : Push dev**

```bash
git push origin dev
```

- [ ] **Step 12.3 : Deploy LXC 303**

```bash
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && ./dev-deploy.sh'"
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && ./dev-deploy.sh'"
```

Attendu : Smoke `/health` ok après les 2 runs (le 2e applique le compose + Dockerfile à jour).

- [ ] **Step 12.4 : Vérification post-deploy**

```bash
# Vérifier que `pgvector` est dans l'image rebuilt
ssh pve "pct exec 303 -- docker run --rm rag-backend:latest uv pip list 2>&1 | grep pgvector"
# Attendu : pgvector  0.3.x

# Vérifier que RealIndexer est dans les logs de boot
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && docker compose -f docker-compose-dev.yml logs backend 2>&1 | grep -E \"sync.worker.started|real_indexer\" | head -5'"

# /version retourne le bon SHA
ssh pve "pct exec 303 -- curl -s http://localhost:8000/version"
```

- [ ] **Step 12.5 : Tag m4a-done**

```bash
git tag m4a-done
git push origin m4a-done
```

- [ ] **Step 12.6 : Bilan**

Lister :
- Commits M4a : `git log m3-done..m4a-done --oneline | wc -l`
- Tests verts (total + délai)
- Coverage globale + par module M4a (`chunking`, `real`, `providers/*`, `workspace_embeddings`)
- Confirmation que `sync.worker.started` apparaît au boot LXC

---

## Récapitulatif M4a

À la fin du jalon, le repo contient (en plus de M3) :

```
backend/src/rag/
├── indexer/
│   ├── chunking.py            # paragraphe + max chars + overlap
│   ├── real.py                # RealIndexer (orchestration)
│   └── providers/
│       ├── protocol.py        # EmbeddingProvider + 4 exceptions
│       ├── openai.py          # OpenAIProvider (batch 100 + retry)
│       ├── voyage.py          # VoyageProvider (input_type=document, batch 128)
│       ├── ollama.py          # OllamaProvider (mono-input séquentiel)
│       └── factory.py         # make_provider dispatch
├── db/
│   └── workspace_embeddings.py # upsert/delete pgvector via pgvector-python
└── main.py                    # RealIndexer remplace NoOpIndexer au lifespan

backend/pyproject.toml         # +pgvector>=0.3
backend/tests/smoke/           # Tests smoke opt-in (3 providers)
backend/README.md              # Doc smoke
```

Sur LXC 303 :
- Le SyncWorker (M3) appelle désormais le **vrai** indexer engine.
- Les bases `rag_<workspace>` se remplissent en chunks pgvector à chaque sync.
- Les compteurs `files_changed` reflètent les indexations effectives.
- Si le provider est down ou rate-limité, le job est marqué `error` (cf. M3 `_format_error`).

M4b peut commencer : API push synchrone (`POST /workspaces/{name}/index` + auth workspace Bearer).

---

## Self-review du plan M4a

### 1. Couverture du spec

| Spec section | Task |
|---|---|
| Dépendance pgvector>=0.3 | T1 |
| chunking.py (algorithme paragraphe + max chars + overlap) | T2 |
| providers/protocol.py (EmbeddingProvider + 4 exceptions) | T3 |
| providers/openai.py (batch 100 + retry 1× sur 429/503/timeout) | T4 |
| providers/voyage.py (input_type=document, batch 128) | T5 |
| providers/ollama.py (mono-input séquentiel, base_url configurable) | T6 |
| providers/factory.py (make_provider dispatch + ValueError) | T7 |
| db/workspace_embeddings.py (DELETE+INSERT en transaction, pgvector-python) | T8 |
| RealIndexer (orchestration index_file + delete_file) | T9 |
| main.py wire-up : RealIndexer remplace NoOpIndexer | T10 |
| Tests smoke opt-in + doc README | T11 |
| Quality gate + smoke deploy + tag m4a-done | T12 |

Couverture complète.

### 2. Cohérence des signatures

- `chunk_text(content, *, max_chars=2000, min_chars=200, overlap_chars=200) -> list[str]` — T2, consommé T9.
- `EmbeddingProvider.embed_texts(texts) -> list[list[float]]` — T3, consommé T4/5/6/9.
- 4 exceptions `Embedding*Error` — T3, consommées T4/5/6/9.
- `make_provider(*, provider, model, api_key, base_url) -> EmbeddingProvider` — T7, consommé T9.
- `upsert_chunks(workspace_pool, *, path, chunks, embeddings) -> int` — T8, consommé T9.
- `delete_chunks_for_path(workspace_pool, path) -> int` / `delete_path(workspace_pool, path) -> None` — T8, consommés T9.
- `RealIndexer(*, config_pool, pool_registry, secret_resolver, provider_factory=make_provider)` — T9, consommé T10.

Toutes signatures consistantes.

### 3. Placeholders scan

Recherche manuelle de "TBD"/"TODO"/"implement later"/"appropriate"/"Similar to" : aucun trouvé.

### 4. Estimation

- T1 : 15 min (ajout dépendance + sync)
- T2 : 1h30 (chunking + 10 tests unit + edge cases)
- T3 : 30 min (Protocol + 4 exceptions + tests)
- T4 : 2h (OpenAIProvider + 6 tests httpx.MockTransport)
- T5 : 45 min (VoyageProvider + 2 tests — structure identique à T4)
- T6 : 1h (OllamaProvider + 3 tests — boucle séquentielle)
- T7 : 30 min (factory + 5 tests)
- T8 : 1h30 (workspace_embeddings + 7 tests intégration pgvector — fixture custom)
- T9 : 2h30 (RealIndexer + 5 tests E2E avec fixture complète setup_workspace_with_embeddings_db)
- T10 : 45 min (main.py wire-up + test wireup + possible adaptation tests E2E M3)
- T11 : 30 min (smoke opt-in + README)
- T12 : 1h (quality gate + smoke deploy + tag)

**Total estimé : ~12-13h** soit ~1.5-2 jours de travail focalisé.
