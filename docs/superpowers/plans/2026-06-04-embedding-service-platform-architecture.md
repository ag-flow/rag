# Embedding Service/Platform Architecture — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructurer `indexer/providers/` en couches Service + Platform + Adapter, et ajouter Azure AI Foundry comme plateforme (embeddings voyage-3.5/4/4-lite + LLM via llm_clients).

**Architecture:** `EmbeddingService` encode le payload/parsing/batch ; `EmbeddingPlatform` encode l'URL + auth ; `EmbeddingProviderAdapter` les compose et gère batching, retry, error-mapping. `BearerPlatform` couvre tous les accès directs + Azure Foundry. `AzureOpenAIPlatform` gère le cas spécial (header `api-key`, strip `model`).

**Tech Stack:** Python 3.12 / httpx async / pytest-asyncio / asyncpg

---

## Fichiers créés / modifiés / supprimés

### Créés
```
backend/src/rag/indexer/providers/services/__init__.py
backend/src/rag/indexer/providers/services/protocol.py
backend/src/rag/indexer/providers/services/openai_compatible.py
backend/src/rag/indexer/providers/services/voyage.py
backend/src/rag/indexer/providers/services/jina.py
backend/src/rag/indexer/providers/services/ollama.py
backend/src/rag/indexer/providers/services/dashscope.py
backend/src/rag/indexer/providers/platforms/__init__.py
backend/src/rag/indexer/providers/platforms/protocol.py
backend/src/rag/indexer/providers/platforms/bearer.py
backend/src/rag/indexer/providers/platforms/azure_openai.py
backend/src/rag/indexer/providers/platforms/ollama.py
backend/src/rag/indexer/providers/adapter.py
backend/migrations/037_add_service_to_model_dimensions.sql
backend/migrations/038_embedding_models_azure_foundry.sql
backend/tests/unit/test_service_openai_compatible.py
backend/tests/unit/test_service_voyage.py
backend/tests/unit/test_service_jina.py
backend/tests/unit/test_service_ollama.py
backend/tests/unit/test_service_dashscope.py
backend/tests/unit/test_platform_bearer.py
backend/tests/unit/test_platform_azure_openai.py
backend/tests/unit/test_platform_ollama.py
backend/tests/unit/test_adapter.py
```

### Modifiés
```
backend/src/rag/indexer/providers/factory.py
backend/src/rag/indexer/real.py
backend/src/rag/api/playground.py
backend/src/rag/services/mcp.py
backend/src/rag/api/mcp_standard.py
backend/src/rag/services/llm_clients.py
backend/tests/unit/test_provider_factory.py
specs/05-indexers.md
```

### Supprimés (Task 12)
```
backend/src/rag/indexer/providers/openai.py
backend/src/rag/indexer/providers/voyage.py
backend/src/rag/indexer/providers/azure_openai.py
backend/src/rag/indexer/providers/ollama.py
backend/src/rag/indexer/providers/mistral.py
backend/src/rag/indexer/providers/jina.py
backend/src/rag/indexer/providers/gemini.py
backend/src/rag/indexer/providers/dashscope.py
backend/tests/unit/test_provider_azure_openai.py
```

---

## Task 1 : Migrations 037 + 038

**Files:**
- Create: `backend/migrations/037_add_service_to_model_dimensions.sql`
- Create: `backend/migrations/038_embedding_models_azure_foundry.sql`

- [ ] **Créer la migration 037**

```sql
-- backend/migrations/037_add_service_to_model_dimensions.sql
-- Migration 037 — colonne service dans model_dimensions
-- Identifie la capacité IA (service) indépendamment de la plateforme d'accès (provider).

ALTER TABLE model_dimensions ADD COLUMN service TEXT NOT NULL DEFAULT '';

UPDATE model_dimensions SET service = provider
    WHERE provider IN ('openai', 'voyage', 'mistral', 'jina', 'gemini', 'ollama', 'dashscope');

UPDATE model_dimensions SET service = 'openai'
    WHERE provider = 'azure-openai';
```

- [ ] **Créer la migration 038**

```sql
-- backend/migrations/038_embedding_models_azure_foundry.sql
-- Migration 038 — modèles Voyage AI accessibles via Azure AI Foundry

INSERT INTO model_dimensions (provider, model, dimension, service) VALUES
    ('azure-foundry', 'voyage-3.5',    1024, 'voyage'),
    ('azure-foundry', 'voyage-4',      1024, 'voyage'),
    ('azure-foundry', 'voyage-4-lite',  512, 'voyage')
ON CONFLICT DO NOTHING;
```

- [ ] **Appliquer les migrations**

```bash
cd backend && uv run python -m rag.db.migrations
```

Résultat attendu : `migrations 037, 038 applied` (ou équivalent selon le runner).

- [ ] **Commit**

```bash
git add backend/migrations/037_add_service_to_model_dimensions.sql \
        backend/migrations/038_embedding_models_azure_foundry.sql
git commit -m "feat(db): migration 037 service dans model_dimensions + 038 azure-foundry models"
```

---

## Task 2 : Services — protocol + OpenAICompatibleService (TDD)

**Files:**
- Create: `backend/src/rag/indexer/providers/services/__init__.py`
- Create: `backend/src/rag/indexer/providers/services/protocol.py`
- Create: `backend/src/rag/indexer/providers/services/openai_compatible.py`
- Create: `backend/tests/unit/test_service_openai_compatible.py`

- [ ] **Écrire les tests (rouge)**

```python
# backend/tests/unit/test_service_openai_compatible.py
from __future__ import annotations

from rag.indexer.providers.services.openai_compatible import OpenAICompatibleService


def test_batch_size() -> None:
    svc = OpenAICompatibleService()
    assert svc.batch_size == 100


def test_embeddings_path() -> None:
    svc = OpenAICompatibleService()
    assert svc.embeddings_path == "/embeddings"


def test_build_document_payload() -> None:
    svc = OpenAICompatibleService()
    payload = svc.build_document_payload(["hello", "world"], "text-embedding-3-small")
    assert payload == {"model": "text-embedding-3-small", "input": ["hello", "world"]}


def test_build_query_payload() -> None:
    svc = OpenAICompatibleService()
    payload = svc.build_query_payload("ma requête", "text-embedding-3-small")
    assert payload == {"model": "text-embedding-3-small", "input": ["ma requête"]}


def test_parse_response_sorted_by_index() -> None:
    svc = OpenAICompatibleService()
    data = {
        "data": [
            {"index": 1, "embedding": [0.2, 0.2]},
            {"index": 0, "embedding": [0.1, 0.1]},
        ]
    }
    result = svc.parse_response(data)
    assert result == [[0.1, 0.1], [0.2, 0.2]]


def test_parse_response_empty_data() -> None:
    svc = OpenAICompatibleService()
    assert svc.parse_response({"data": []}) == []
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_service_openai_compatible.py -v 2>&1 | head -5
```

Résultat attendu : `ImportError` (module inexistant).

- [ ] **Créer `services/__init__.py` (vide)**

```python
# backend/src/rag/indexer/providers/services/__init__.py
```

- [ ] **Créer `services/protocol.py`**

```python
# backend/src/rag/indexer/providers/services/protocol.py
from __future__ import annotations

from typing import ClassVar, Protocol


class EmbeddingService(Protocol):
    """Capacité IA : payload, parsing, batch_size.

    Indépendant de la plateforme d'accès (URL, auth).
    """

    batch_size: ClassVar[int]
    embeddings_path: ClassVar[str]

    def build_document_payload(self, texts: list[str], model: str) -> dict: ...
    def build_query_payload(self, text: str, model: str) -> dict: ...
    def parse_response(self, data: dict) -> list[list[float]]: ...
```

- [ ] **Créer `services/openai_compatible.py`**

```python
# backend/src/rag/indexer/providers/services/openai_compatible.py
from __future__ import annotations

from typing import Any, ClassVar


class OpenAICompatibleService:
    """Service d'embedding au format OpenAI standard.

    Payload : {model, input: list[str]}.
    Réponse : {data: [{index, embedding}]}.
    Utilisé par : openai, mistral, gemini, azure-foundry (openai models).
    """

    batch_size: ClassVar[int] = 100
    embeddings_path: ClassVar[str] = "/embeddings"

    def build_document_payload(self, texts: list[str], model: str) -> dict[str, Any]:
        return {"model": model, "input": texts}

    def build_query_payload(self, text: str, model: str) -> dict[str, Any]:
        return {"model": model, "input": [text]}

    def parse_response(self, data: dict[str, Any]) -> list[list[float]]:
        items = data.get("data", [])
        return [
            item["embedding"]
            for item in sorted(items, key=lambda x: x.get("index", 0))
        ]
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_service_openai_compatible.py -v
```

Résultat attendu : 6 tests PASS.

- [ ] **Commit**

```bash
git add backend/src/rag/indexer/providers/services/ \
        backend/tests/unit/test_service_openai_compatible.py
git commit -m "feat(indexer): services protocol + OpenAICompatibleService"
```

---

## Task 3 : VoyageService (TDD)

**Files:**
- Create: `backend/src/rag/indexer/providers/services/voyage.py`
- Create: `backend/tests/unit/test_service_voyage.py`

- [ ] **Écrire les tests (rouge)**

```python
# backend/tests/unit/test_service_voyage.py
from __future__ import annotations

from rag.indexer.providers.services.voyage import VoyageService


def test_batch_size() -> None:
    assert VoyageService.batch_size == 128


def test_embeddings_path() -> None:
    assert VoyageService.embeddings_path == "/embeddings"


def test_document_payload_has_input_type_document() -> None:
    svc = VoyageService()
    payload = svc.build_document_payload(["doc1", "doc2"], "voyage-4")
    assert payload == {"model": "voyage-4", "input": ["doc1", "doc2"], "input_type": "document"}


def test_query_payload_has_input_type_query() -> None:
    svc = VoyageService()
    payload = svc.build_query_payload("ma requête", "voyage-4")
    assert payload == {"model": "voyage-4", "input": ["ma requête"], "input_type": "query"}


def test_parse_response_same_as_openai_compatible() -> None:
    svc = VoyageService()
    data = {"data": [{"index": 0, "embedding": [0.1, 0.2]}, {"index": 1, "embedding": [0.3, 0.4]}]}
    result = svc.parse_response(data)
    assert result == [[0.1, 0.2], [0.3, 0.4]]
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_service_voyage.py -v 2>&1 | head -5
```

Résultat attendu : `ImportError`.

- [ ] **Créer `services/voyage.py`**

```python
# backend/src/rag/indexer/providers/services/voyage.py
from __future__ import annotations

from typing import Any, ClassVar

from rag.indexer.providers.services.openai_compatible import OpenAICompatibleService


class VoyageService(OpenAICompatibleService):
    """Service Voyage AI — ajoute input_type pour optimiser document vs query.

    Utilisé via voyage platform (direct) ou azure-foundry platform.
    """

    batch_size: ClassVar[int] = 128

    def build_document_payload(self, texts: list[str], model: str) -> dict[str, Any]:
        return {"model": model, "input": texts, "input_type": "document"}

    def build_query_payload(self, text: str, model: str) -> dict[str, Any]:
        return {"model": model, "input": [text], "input_type": "query"}
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_service_voyage.py -v
```

Résultat attendu : 5 tests PASS.

- [ ] **Commit**

```bash
git add backend/src/rag/indexer/providers/services/voyage.py \
        backend/tests/unit/test_service_voyage.py
git commit -m "feat(indexer): VoyageService — input_type document/query"
```

---

## Task 4 : JinaService (TDD)

**Files:**
- Create: `backend/src/rag/indexer/providers/services/jina.py`
- Create: `backend/tests/unit/test_service_jina.py`

- [ ] **Écrire les tests (rouge)**

```python
# backend/tests/unit/test_service_jina.py
from __future__ import annotations

from rag.indexer.providers.services.jina import JinaService


def test_document_payload_has_task_retrieval_passage() -> None:
    svc = JinaService()
    payload = svc.build_document_payload(["doc1"], "jina-embeddings-v3")
    assert payload == {"model": "jina-embeddings-v3", "input": ["doc1"], "task": "retrieval.passage"}


def test_query_payload_has_task_retrieval_query() -> None:
    svc = JinaService()
    payload = svc.build_query_payload("question", "jina-embeddings-v3")
    assert payload == {"model": "jina-embeddings-v3", "input": ["question"], "task": "retrieval.query"}


def test_batch_size_and_path_inherited() -> None:
    svc = JinaService()
    assert svc.batch_size == 100
    assert svc.embeddings_path == "/embeddings"
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_service_jina.py -v 2>&1 | head -5
```

- [ ] **Créer `services/jina.py`**

```python
# backend/src/rag/indexer/providers/services/jina.py
from __future__ import annotations

from typing import Any

from rag.indexer.providers.services.openai_compatible import OpenAICompatibleService


class JinaService(OpenAICompatibleService):
    """Service Jina AI — ajoute task pour document vs query.

    task="retrieval.passage" pour l'indexation, "retrieval.query" pour la recherche.
    """

    def build_document_payload(self, texts: list[str], model: str) -> dict[str, Any]:
        return {"model": model, "input": texts, "task": "retrieval.passage"}

    def build_query_payload(self, text: str, model: str) -> dict[str, Any]:
        return {"model": model, "input": [text], "task": "retrieval.query"}
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_service_jina.py -v
```

Résultat attendu : 3 tests PASS.

- [ ] **Commit**

```bash
git add backend/src/rag/indexer/providers/services/jina.py \
        backend/tests/unit/test_service_jina.py
git commit -m "feat(indexer): JinaService — task retrieval.passage/query"
```

---

## Task 5 : OllamaService (TDD)

**Files:**
- Create: `backend/src/rag/indexer/providers/services/ollama.py`
- Create: `backend/tests/unit/test_service_ollama.py`

- [ ] **Écrire les tests (rouge)**

```python
# backend/tests/unit/test_service_ollama.py
from __future__ import annotations

import pytest

from rag.indexer.providers.services.ollama import OllamaService


def test_batch_size_is_one() -> None:
    assert OllamaService.batch_size == 1


def test_embeddings_path_is_empty() -> None:
    assert OllamaService.embeddings_path == ""


def test_document_payload_takes_first_text() -> None:
    svc = OllamaService()
    payload = svc.build_document_payload(["seul texte"], "qwen2.5-coder:14b")
    assert payload == {"model": "qwen2.5-coder:14b", "input": "seul texte"}


def test_query_payload_is_string() -> None:
    svc = OllamaService()
    payload = svc.build_query_payload("ma requête", "qwen2.5-coder:14b")
    assert payload == {"model": "qwen2.5-coder:14b", "input": "ma requête"}


def test_parse_response_returns_single_vector() -> None:
    svc = OllamaService()
    data = {"embeddings": [[0.1, 0.2, 0.3]]}
    result = svc.parse_response(data)
    assert result == [[0.1, 0.2, 0.3]]


def test_parse_response_missing_embeddings_raises() -> None:
    svc = OllamaService()
    with pytest.raises(RuntimeError, match="embeddings"):
        svc.parse_response({"embeddings": []})
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_service_ollama.py -v 2>&1 | head -5
```

- [ ] **Créer `services/ollama.py`**

```python
# backend/src/rag/indexer/providers/services/ollama.py
from __future__ import annotations

from typing import Any, ClassVar


class OllamaService:
    """Service Ollama — API /api/embed, mono-input, réponse {embeddings: [[...]]}.

    batch_size=1 : l'adapter découpera toujours en batches d'un seul texte.
    embeddings_path="" : OllamaPlatform.url() ignore le path et retourne toujours /api/embed.
    """

    batch_size: ClassVar[int] = 1
    embeddings_path: ClassVar[str] = ""

    def build_document_payload(self, texts: list[str], model: str) -> dict[str, Any]:
        return {"model": model, "input": texts[0]}

    def build_query_payload(self, text: str, model: str) -> dict[str, Any]:
        return {"model": model, "input": text}

    def parse_response(self, data: dict[str, Any]) -> list[list[float]]:
        embeddings = data.get("embeddings", [])
        if not embeddings or not isinstance(embeddings[0], list):
            raise RuntimeError("Ollama response missing valid 'embeddings' field")
        return [embeddings[0]]
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_service_ollama.py -v
```

Résultat attendu : 6 tests PASS.

- [ ] **Commit**

```bash
git add backend/src/rag/indexer/providers/services/ollama.py \
        backend/tests/unit/test_service_ollama.py
git commit -m "feat(indexer): OllamaService — mono-input, réponse embeddings[]"
```

---

## Task 6 : DashScopeService (TDD)

**Files:**
- Create: `backend/src/rag/indexer/providers/services/dashscope.py`
- Create: `backend/tests/unit/test_service_dashscope.py`

- [ ] **Écrire les tests (rouge)**

```python
# backend/tests/unit/test_service_dashscope.py
from __future__ import annotations

from rag.indexer.providers.services.dashscope import DashScopeService


def test_batch_size_is_25() -> None:
    assert DashScopeService.batch_size == 25


def test_embeddings_path_is_empty() -> None:
    assert DashScopeService.embeddings_path == ""


def test_document_payload_format() -> None:
    svc = DashScopeService()
    payload = svc.build_document_payload(["a", "b"], "text-embedding-v3")
    assert payload == {"model": "text-embedding-v3", "input": {"texts": ["a", "b"]}}


def test_query_payload_format() -> None:
    svc = DashScopeService()
    payload = svc.build_query_payload("question", "text-embedding-v3")
    assert payload == {"model": "text-embedding-v3", "input": {"texts": ["question"]}}


def test_parse_response_sorted_by_text_index() -> None:
    svc = DashScopeService()
    data = {
        "output": {
            "embeddings": [
                {"text_index": 1, "embedding": [0.2, 0.2]},
                {"text_index": 0, "embedding": [0.1, 0.1]},
            ]
        }
    }
    result = svc.parse_response(data)
    assert result == [[0.1, 0.1], [0.2, 0.2]]
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_service_dashscope.py -v 2>&1 | head -5
```

- [ ] **Créer `services/dashscope.py`**

```python
# backend/src/rag/indexer/providers/services/dashscope.py
from __future__ import annotations

from typing import Any, ClassVar


class DashScopeService:
    """Service Alibaba DashScope — format natif non-OpenAI.

    Payload : {model, input: {texts: list[str]}}.
    Réponse : {output: {embeddings: [{text_index, embedding}]}}.
    batch_size=25 (limite DashScope).
    embeddings_path="" : BearerPlatform(FULL_URL, key).url("") = FULL_URL.
    """

    batch_size: ClassVar[int] = 25
    embeddings_path: ClassVar[str] = ""

    def build_document_payload(self, texts: list[str], model: str) -> dict[str, Any]:
        return {"model": model, "input": {"texts": texts}}

    def build_query_payload(self, text: str, model: str) -> dict[str, Any]:
        return {"model": model, "input": {"texts": [text]}}

    def parse_response(self, data: dict[str, Any]) -> list[list[float]]:
        items = data.get("output", {}).get("embeddings", [])
        return [
            item["embedding"]
            for item in sorted(items, key=lambda x: x.get("text_index", 0))
        ]
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_service_dashscope.py -v
```

Résultat attendu : 5 tests PASS.

- [ ] **Commit**

```bash
git add backend/src/rag/indexer/providers/services/dashscope.py \
        backend/tests/unit/test_service_dashscope.py
git commit -m "feat(indexer): DashScopeService — format natif Alibaba"
```

---

## Task 7 : Platforms — protocol + BearerPlatform (TDD)

**Files:**
- Create: `backend/src/rag/indexer/providers/platforms/__init__.py`
- Create: `backend/src/rag/indexer/providers/platforms/protocol.py`
- Create: `backend/src/rag/indexer/providers/platforms/bearer.py`
- Create: `backend/tests/unit/test_platform_bearer.py`

- [ ] **Écrire les tests (rouge)**

```python
# backend/tests/unit/test_platform_bearer.py
from __future__ import annotations

import pytest

from rag.indexer.providers.platforms.bearer import BearerPlatform
from rag.indexer.providers.protocol import EmbeddingAuthError


def test_auth_headers_bearer() -> None:
    p = BearerPlatform("https://api.openai.com/v1", "sk-test")
    assert p.auth_headers() == {"Authorization": "Bearer sk-test"}


def test_url_appends_path() -> None:
    p = BearerPlatform("https://api.openai.com/v1", "sk-test")
    assert p.url("/embeddings") == "https://api.openai.com/v1/embeddings"


def test_url_strips_trailing_slash_from_base() -> None:
    p = BearerPlatform("https://api.openai.com/v1/", "sk-test")
    assert p.url("/embeddings") == "https://api.openai.com/v1/embeddings"


def test_url_empty_path_returns_base() -> None:
    p = BearerPlatform("https://example.com/full/path", "key")
    assert p.url("") == "https://example.com/full/path"


def test_modify_payload_is_identity() -> None:
    p = BearerPlatform("https://api.openai.com/v1", "key")
    payload = {"model": "x", "input": ["a"]}
    assert p.modify_payload(payload) == payload


def test_validate_auth_raises_when_key_none() -> None:
    p = BearerPlatform("https://api.openai.com/v1", None)
    with pytest.raises(EmbeddingAuthError):
        p.validate_auth()


def test_validate_auth_passes_when_key_set() -> None:
    p = BearerPlatform("https://api.openai.com/v1", "sk-key")
    p.validate_auth()  # ne lève pas
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_platform_bearer.py -v 2>&1 | head -5
```

- [ ] **Créer `platforms/__init__.py` (vide)**

```python
# backend/src/rag/indexer/providers/platforms/__init__.py
```

- [ ] **Créer `platforms/protocol.py`**

```python
# backend/src/rag/indexer/providers/platforms/protocol.py
from __future__ import annotations

from typing import Protocol


class EmbeddingPlatform(Protocol):
    """Plateforme d'accès : URL + authentification.

    Indépendant du service IA (payload, parsing).
    """

    def auth_headers(self) -> dict[str, str]: ...
    def url(self, path: str) -> str: ...
    def modify_payload(self, payload: dict) -> dict: ...
    def validate_auth(self) -> None: ...
```

- [ ] **Créer `platforms/bearer.py`**

```python
# backend/src/rag/indexer/providers/platforms/bearer.py
from __future__ import annotations

from rag.indexer.providers.protocol import EmbeddingAuthError


class BearerPlatform:
    """Plateforme générique à authentification Bearer.

    Couvre : openai direct, voyage direct, mistral, jina, gemini, dashscope,
    et Azure AI Foundry (base_url fourni par l'utilisateur).
    """

    def __init__(self, base_url: str, api_key: str | None) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def modify_payload(self, payload: dict) -> dict:
        return payload

    def validate_auth(self) -> None:
        if not self._api_key:
            raise EmbeddingAuthError("api_key is required (got None)")
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_platform_bearer.py -v
```

Résultat attendu : 7 tests PASS.

- [ ] **Commit**

```bash
git add backend/src/rag/indexer/providers/platforms/ \
        backend/tests/unit/test_platform_bearer.py
git commit -m "feat(indexer): platforms protocol + BearerPlatform"
```

---

## Task 8 : AzureOpenAIPlatform (TDD)

**Files:**
- Create: `backend/src/rag/indexer/providers/platforms/azure_openai.py`
- Create: `backend/tests/unit/test_platform_azure_openai.py`

- [ ] **Écrire les tests (rouge)**

```python
# backend/tests/unit/test_platform_azure_openai.py
from __future__ import annotations

import pytest

from rag.indexer.providers.platforms.azure_openai import AzureOpenAIPlatform
from rag.indexer.providers.protocol import EmbeddingAuthError

_BASE = "https://myresource.openai.azure.com/openai/deployments/text-embedding-3-small"


def test_auth_header_is_api_key_not_bearer() -> None:
    p = AzureOpenAIPlatform(_BASE, "az-key")
    headers = p.auth_headers()
    assert headers == {"api-key": "az-key"}
    assert "Authorization" not in headers


def test_url_appends_api_version() -> None:
    p = AzureOpenAIPlatform(_BASE, "az-key")
    url = p.url("/embeddings")
    assert url == f"{_BASE}/embeddings?api-version=2024-02-01"


def test_modify_payload_strips_model() -> None:
    p = AzureOpenAIPlatform(_BASE, "az-key")
    payload = {"model": "text-embedding-3-small", "input": ["hello"]}
    result = p.modify_payload(payload)
    assert result == {"input": ["hello"]}
    assert "model" not in result


def test_modify_payload_preserves_other_fields() -> None:
    p = AzureOpenAIPlatform(_BASE, "az-key")
    payload = {"model": "x", "input": ["a"], "input_type": "document"}
    result = p.modify_payload(payload)
    assert result == {"input": ["a"], "input_type": "document"}


def test_validate_auth_raises_when_key_none() -> None:
    p = AzureOpenAIPlatform(_BASE, None)
    with pytest.raises(EmbeddingAuthError):
        p.validate_auth()
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_platform_azure_openai.py -v 2>&1 | head -5
```

- [ ] **Créer `platforms/azure_openai.py`**

```python
# backend/src/rag/indexer/providers/platforms/azure_openai.py
from __future__ import annotations

from rag.indexer.providers.protocol import EmbeddingAuthError

_API_VERSION = "2024-02-01"


class AzureOpenAIPlatform:
    """Plateforme Azure OpenAI Service (deployments).

    Auth : header api-key (pas Authorization: Bearer).
    URL : {base_url}{path}?api-version=2024-02-01
    modify_payload : supprime le champ model (le deployment Azure le définit).
    """

    def __init__(self, base_url: str, api_key: str | None) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def auth_headers(self) -> dict[str, str]:
        return {"api-key": self._api_key or ""}

    def url(self, path: str) -> str:
        return f"{self._base_url}{path}?api-version={_API_VERSION}"

    def modify_payload(self, payload: dict) -> dict:
        return {k: v for k, v in payload.items() if k != "model"}

    def validate_auth(self) -> None:
        if not self._api_key:
            raise EmbeddingAuthError("Azure OpenAI api_key is required (got None)")
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_platform_azure_openai.py -v
```

Résultat attendu : 5 tests PASS.

- [ ] **Commit**

```bash
git add backend/src/rag/indexer/providers/platforms/azure_openai.py \
        backend/tests/unit/test_platform_azure_openai.py
git commit -m "feat(indexer): AzureOpenAIPlatform — api-key header, strip model"
```

---

## Task 9 : OllamaPlatform (TDD)

**Files:**
- Create: `backend/src/rag/indexer/providers/platforms/ollama.py`
- Create: `backend/tests/unit/test_platform_ollama.py`

- [ ] **Écrire les tests (rouge)**

```python
# backend/tests/unit/test_platform_ollama.py
from __future__ import annotations

from rag.indexer.providers.platforms.ollama import OllamaPlatform


def test_auth_headers_empty() -> None:
    p = OllamaPlatform("http://localhost:11434")
    assert p.auth_headers() == {}


def test_url_ignores_path_and_uses_api_embed() -> None:
    p = OllamaPlatform("http://localhost:11434")
    assert p.url("/embeddings") == "http://localhost:11434/api/embed"
    assert p.url("") == "http://localhost:11434/api/embed"


def test_url_strips_trailing_slash_from_base() -> None:
    p = OllamaPlatform("http://localhost:11434/")
    assert p.url("") == "http://localhost:11434/api/embed"


def test_modify_payload_is_identity() -> None:
    p = OllamaPlatform("http://localhost:11434")
    payload = {"model": "x", "input": "hello"}
    assert p.modify_payload(payload) == payload


def test_validate_auth_never_raises() -> None:
    p = OllamaPlatform("http://localhost:11434")
    p.validate_auth()  # pas d'exception
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_platform_ollama.py -v 2>&1 | head -5
```

- [ ] **Créer `platforms/ollama.py`**

```python
# backend/src/rag/indexer/providers/platforms/ollama.py
from __future__ import annotations


class OllamaPlatform:
    """Plateforme Ollama local — pas d'auth, endpoint /api/embed fixe."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def auth_headers(self) -> dict[str, str]:
        return {}

    def url(self, path: str) -> str:  # noqa: ARG002 — path ignoré
        return f"{self._base_url}/api/embed"

    def modify_payload(self, payload: dict) -> dict:
        return payload

    def validate_auth(self) -> None:
        pass
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_platform_ollama.py -v
```

Résultat attendu : 5 tests PASS.

- [ ] **Commit**

```bash
git add backend/src/rag/indexer/providers/platforms/ollama.py \
        backend/tests/unit/test_platform_ollama.py
git commit -m "feat(indexer): OllamaPlatform — no auth, url /api/embed"
```

---

## Task 10 : EmbeddingProviderAdapter (TDD)

**Files:**
- Create: `backend/src/rag/indexer/providers/adapter.py`
- Create: `backend/tests/unit/test_adapter.py`

- [ ] **Écrire les tests (rouge)**

```python
# backend/tests/unit/test_adapter.py
from __future__ import annotations

import json

import httpx
import pytest

from rag.indexer.providers.adapter import EmbeddingProviderAdapter
from rag.indexer.providers.platforms.bearer import BearerPlatform
from rag.indexer.providers.protocol import (
    EmbeddingAuthError,
    EmbeddingProviderUnreachable,
    EmbeddingRateLimited,
)
from rag.indexer.providers.services.openai_compatible import OpenAICompatibleService
from rag.indexer.providers.services.voyage import VoyageService

_BASE = "https://api.example.com/v1"
_KEY = "test-key"


def _make_adapter(*, service=None, platform=None, model="test-model", transport=None, retry_sleep=0.0):
    svc = service or OpenAICompatibleService()
    plat = platform or BearerPlatform(_BASE, _KEY)
    return EmbeddingProviderAdapter(
        service=svc,
        platform=plat,
        model=model,
        transport=transport,
        retry_sleep_seconds=retry_sleep,
    )


def _ok_response(texts: list[str], dim: int = 4) -> httpx.Response:
    data = [{"embedding": [0.1] * dim, "index": i} for i in range(len(texts))]
    return httpx.Response(200, json={"data": data})


@pytest.mark.asyncio
async def test_embed_texts_empty_returns_empty() -> None:
    adapter = _make_adapter()
    result = await adapter.embed_texts([])
    assert result == []


@pytest.mark.asyncio
async def test_embed_texts_success_url_headers_body() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return _ok_response(captured["body"]["input"])

    adapter = _make_adapter(transport=httpx.MockTransport(handler))
    result = await adapter.embed_texts(["hello", "world"])

    assert len(result) == 2
    assert len(result[0]) == 4
    assert captured["url"] == f"{_BASE}/embeddings"
    assert captured["headers"]["authorization"] == f"Bearer {_KEY}"
    assert captured["body"] == {"model": "test-model", "input": ["hello", "world"]}


@pytest.mark.asyncio
async def test_embed_texts_batches_at_service_batch_size() -> None:
    batches: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        batches.append(len(body["input"]))
        data = [{"embedding": [0.1], "index": i} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": data})

    adapter = _make_adapter(transport=httpx.MockTransport(handler))
    # OpenAICompatibleService.batch_size = 100
    texts = [f"t{i}" for i in range(150)]
    result = await adapter.embed_texts(texts)
    assert len(result) == 150
    assert batches == [100, 50]


@pytest.mark.asyncio
async def test_embed_texts_no_api_key_raises_auth_error() -> None:
    adapter = _make_adapter(platform=BearerPlatform(_BASE, None))
    with pytest.raises(EmbeddingAuthError):
        await adapter.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_embed_texts_401_raises_auth_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Unauthorized"})

    adapter = _make_adapter(transport=httpx.MockTransport(handler))
    with pytest.raises(EmbeddingAuthError):
        await adapter.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_embed_texts_429_retries_once_then_raises_rate_limited() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"error": "Rate limit"})

    adapter = _make_adapter(transport=httpx.MockTransport(handler), retry_sleep=0.0)
    with pytest.raises(EmbeddingRateLimited):
        await adapter.embed_texts(["hello"])
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_embed_texts_503_retries_once_then_raises_unreachable() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={"error": "Down"})

    adapter = _make_adapter(transport=httpx.MockTransport(handler), retry_sleep=0.0)
    with pytest.raises(EmbeddingProviderUnreachable):
        await adapter.embed_texts(["hello"])
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_embed_texts_timeout_retries_once_then_raises_unreachable() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.TimeoutException("timeout")

    adapter = _make_adapter(transport=httpx.MockTransport(handler), retry_sleep=0.0)
    with pytest.raises(EmbeddingProviderUnreachable):
        await adapter.embed_texts(["hello"])
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_embed_query_uses_build_query_payload() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2], "index": 0}]})

    adapter = _make_adapter(
        service=VoyageService(),
        transport=httpx.MockTransport(handler),
        model="voyage-4",
    )
    result = await adapter.embed_query("ma requête")
    assert result == [0.1, 0.2]
    assert captured["body"]["input_type"] == "query"
    assert captured["body"]["input"] == ["ma requête"]


@pytest.mark.asyncio
async def test_azure_openai_platform_strips_model_from_payload() -> None:
    from rag.indexer.providers.platforms.azure_openai import AzureOpenAIPlatform

    captured: dict = {}
    _AZ_BASE = "https://res.openai.azure.com/openai/deployments/emb"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        body = json.loads(request.content)
        data = [{"embedding": [0.1], "index": i} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": data})

    adapter = EmbeddingProviderAdapter(
        service=OpenAICompatibleService(),
        platform=AzureOpenAIPlatform(_AZ_BASE, "az-key"),
        model="text-embedding-3-small",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0.0,
    )
    await adapter.embed_texts(["hello"])

    assert "model" not in captured["body"]
    assert captured["headers"]["api-key"] == "az-key"
    assert "api-version=2024-02-01" in captured["url"]
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_adapter.py -v 2>&1 | head -5
```

Résultat attendu : `ImportError` (adapter.py inexistant).

- [ ] **Créer `adapter.py`**

```python
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
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_adapter.py -v
```

Résultat attendu : 11 tests PASS.

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/indexer/providers/adapter.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/indexer/providers/adapter.py \
        backend/tests/unit/test_adapter.py
git commit -m "feat(indexer): EmbeddingProviderAdapter — batching, retry, error mapping"
```

---

## Task 11 : Factory rewrite + mise à jour des callers

**Files:**
- Modify: `backend/src/rag/indexer/providers/factory.py`
- Modify: `backend/tests/unit/test_provider_factory.py`
- Modify: `backend/src/rag/indexer/real.py`
- Modify: `backend/src/rag/api/playground.py`
- Modify: `backend/src/rag/services/mcp.py`
- Modify: `backend/src/rag/api/mcp_standard.py`

### Étape 1 — Réécrire test_provider_factory.py (rouge)

- [ ] **Remplacer le contenu de `backend/tests/unit/test_provider_factory.py`**

```python
# backend/tests/unit/test_provider_factory.py
from __future__ import annotations

import pytest

from rag.indexer.providers.adapter import EmbeddingProviderAdapter
from rag.indexer.providers.factory import make_provider


def _make(**kwargs):
    defaults = dict(service="openai", provider="openai", model="text-embedding-3-small",
                    api_key="sk-x", base_url=None)
    defaults.update(kwargs)
    return make_provider(**defaults)


def test_openai_direct_returns_adapter() -> None:
    p = _make(service="openai", provider="openai")
    assert isinstance(p, EmbeddingProviderAdapter)


def test_voyage_direct_returns_adapter() -> None:
    p = _make(service="voyage", provider="voyage", model="voyage-3", api_key="vk-x")
    assert isinstance(p, EmbeddingProviderAdapter)


def test_mistral_returns_adapter() -> None:
    p = _make(service="mistral", provider="mistral", model="mistral-embed")
    assert isinstance(p, EmbeddingProviderAdapter)


def test_jina_returns_adapter() -> None:
    p = _make(service="jina", provider="jina", model="jina-embeddings-v3")
    assert isinstance(p, EmbeddingProviderAdapter)


def test_gemini_returns_adapter() -> None:
    p = _make(service="gemini", provider="gemini", model="gemini-embedding-001")
    assert isinstance(p, EmbeddingProviderAdapter)


def test_dashscope_returns_adapter() -> None:
    p = _make(service="dashscope", provider="dashscope", model="text-embedding-v3")
    assert isinstance(p, EmbeddingProviderAdapter)


def test_ollama_returns_adapter() -> None:
    p = _make(service="ollama", provider="ollama", model="nomic-embed-text", api_key=None)
    assert isinstance(p, EmbeddingProviderAdapter)


def test_ollama_no_base_url_uses_default() -> None:
    p = _make(service="ollama", provider="ollama", model="nomic-embed-text", api_key=None)
    assert isinstance(p, EmbeddingProviderAdapter)


def test_azure_openai_returns_adapter() -> None:
    p = _make(
        service="openai", provider="azure-openai",
        base_url="https://res.openai.azure.com/openai/deployments/emb",
    )
    assert isinstance(p, EmbeddingProviderAdapter)


def test_azure_openai_without_base_url_raises() -> None:
    with pytest.raises(ValueError, match="base_url"):
        _make(service="openai", provider="azure-openai", base_url=None)


def test_azure_foundry_voyage_returns_adapter() -> None:
    p = _make(
        service="voyage", provider="azure-foundry",
        model="voyage-4",
        base_url="https://name.region.models.ai.azure.com/v1",
    )
    assert isinstance(p, EmbeddingProviderAdapter)


def test_azure_foundry_without_base_url_raises() -> None:
    with pytest.raises(ValueError, match="base_url"):
        _make(service="voyage", provider="azure-foundry", base_url=None)


def test_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported provider"):
        _make(provider="cohere")


def test_unknown_service_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported service"):
        _make(service="unknown-svc")
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_provider_factory.py -v 2>&1 | head -10
```

Résultat attendu : FAILED (`make_provider() got unexpected keyword argument 'service'`).

### Étape 2 — Réécrire factory.py

- [ ] **Remplacer le contenu de `backend/src/rag/indexer/providers/factory.py`**

```python
# backend/src/rag/indexer/providers/factory.py
from __future__ import annotations

from rag.indexer.providers.adapter import EmbeddingProviderAdapter
from rag.indexer.providers.platforms.azure_openai import AzureOpenAIPlatform
from rag.indexer.providers.platforms.bearer import BearerPlatform
from rag.indexer.providers.platforms.ollama import OllamaPlatform
from rag.indexer.providers.protocol import EmbeddingProvider
from rag.indexer.providers.services.dashscope import DashScopeService
from rag.indexer.providers.services.jina import JinaService
from rag.indexer.providers.services.ollama import OllamaService
from rag.indexer.providers.services.openai_compatible import OpenAICompatibleService
from rag.indexer.providers.services.voyage import VoyageService

_DIRECT_URLS: dict[str, str] = {
    "openai":    "https://api.openai.com/v1",
    "voyage":    "https://api.voyageai.com/v1",
    "mistral":   "https://api.mistral.ai/v1",
    "jina":      "https://api.jina.ai/v1",
    "gemini":    "https://generativelanguage.googleapis.com/v1beta/openai",
    "dashscope": "https://dashscope-intl.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding",
}

_OLLAMA_DEFAULT_BASE_URL = "http://192.168.10.80:11434"


def make_provider(
    *,
    service: str,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
) -> EmbeddingProvider:
    """Construit un EmbeddingProvider à partir du service + provider configurés.

    service  : capacité IA (openai, voyage, jina, dashscope, ollama, mistral, gemini).
               Disponible dans model_dimensions.service.
    provider : plateforme d'accès (openai, voyage, mistral, jina, gemini,
               dashscope, ollama, azure-openai, azure-foundry).
    """
    svc = _make_service(service)
    plat = _make_platform(provider, api_key=api_key, base_url=base_url)
    return EmbeddingProviderAdapter(service=svc, platform=plat, model=model)


def _make_service(service: str):
    if service in ("openai", "mistral", "gemini"):
        return OpenAICompatibleService()
    if service == "voyage":
        return VoyageService()
    if service == "jina":
        return JinaService()
    if service == "dashscope":
        return DashScopeService()
    if service == "ollama":
        return OllamaService()
    raise ValueError(f"Unsupported service: {service!r}")


def _make_platform(provider: str, *, api_key: str | None, base_url: str | None):
    if provider == "azure-openai":
        if not base_url:
            raise ValueError(
                "azure-openai provider requires base_url "
                "(https://{resource}.openai.azure.com/openai/deployments/{deployment_name})"
            )
        return AzureOpenAIPlatform(base_url, api_key)
    if provider == "azure-foundry":
        if not base_url:
            raise ValueError(
                "azure-foundry provider requires base_url "
                "(https://{name}.{region}.models.ai.azure.com/v1)"
            )
        return BearerPlatform(base_url, api_key)
    if provider == "ollama":
        return OllamaPlatform(base_url or _OLLAMA_DEFAULT_BASE_URL)
    if provider in _DIRECT_URLS:
        return BearerPlatform(_DIRECT_URLS[provider], api_key)
    raise ValueError(f"Unsupported provider: {provider!r}")
```

- [ ] **Vérifier que les tests factory passent**

```bash
cd backend && uv run pytest tests/unit/test_provider_factory.py -v
```

Résultat attendu : 14 tests PASS.

### Étape 3 — Mettre à jour real.py

- [ ] **Modifier la query dans `_load_workspace_context` (`backend/src/rag/indexer/real.py:196-223`)**

Remplacer la query SQL par :

```python
        row = await self._config_pool.fetchrow(
            """
            SELECT
                w.name AS workspace_name,
                w.rag_cnx AS rag_cnx,
                ic.provider AS provider,
                ic.model AS model,
                ic.api_key_ref AS api_key_ref,
                ic.base_url AS base_url,
                md.service AS service,
                cc.strategy AS chunking_strategy,
                cc.max_chars AS chunking_max_chars,
                cc.min_chars AS chunking_min_chars,
                cc.overlap_chars AS chunking_overlap_chars,
                cc.extras AS chunking_extras
            FROM workspaces w
            JOIN indexer_configs ic ON ic.workspace_id = w.id
            JOIN model_dimensions md ON md.provider = ic.provider AND md.model = ic.model
            JOIN chunking_configs cc ON cc.workspace_id = w.id
            WHERE w.id = $1
            """,
            workspace_id,
        )
```

- [ ] **Modifier l'appel `make_provider` dans `real.py:126-131`**

```python
        provider = self._provider_factory(
            service=ctx["service"],
            provider=ctx["provider"],
            model=ctx["model"],
            api_key=api_key,
            base_url=ctx["base_url"],
        )
```

### Étape 4 — Mettre à jour playground.py

- [ ] **Modifier la query dans `playground_chat` (`backend/src/rag/api/playground.py:125-135`)**

```python
        ws_row = await conn.fetchrow(
            """
            SELECT w.rag_cnx, w.name AS ws_name,
                   ic.provider AS idx_provider, ic.model AS idx_model,
                   ic.api_key_ref AS idx_api_key_ref, ic.base_url AS idx_base_url,
                   md.service AS idx_service
            FROM workspaces w
            JOIN indexer_configs ic ON ic.workspace_id = w.id
            JOIN model_dimensions md ON md.provider = ic.provider AND md.model = ic.model
            WHERE w.name = $1
            """,
            workspace_name,
        )
```

- [ ] **Modifier l'appel `make_provider` dans `playground.py:158-163`**

```python
    embedding_provider = make_provider(
        service=ws_row["idx_service"],
        provider=ws_row["idx_provider"],
        model=ws_row["idx_model"],
        api_key=indexer_api_key,
        base_url=ws_row["idx_base_url"],
    )
```

### Étape 5 — Mettre à jour mcp.py

- [ ] **Modifier `_load_workspace_context` dans `backend/src/rag/services/mcp.py:147-165`**

```python
    row = await config_pool.fetchrow(
        """
        SELECT
            w.name AS workspace_name,
            w.rag_cnx AS rag_cnx,
            ic.provider AS provider,
            ic.model AS model,
            ic.api_key_ref AS api_key_ref,
            ic.base_url AS base_url,
            md.service AS service,
            rc.provider AS rerank_provider,
            rc.model AS rerank_model,
            rc.api_key_ref AS rerank_api_key_ref,
            rc.base_url AS rerank_base_url,
            rc.top_k_pre_rerank AS rerank_top_k_pre_rerank
        FROM workspaces w
        JOIN indexer_configs ic ON ic.workspace_id = w.id
        JOIN model_dimensions md ON md.provider = ic.provider AND md.model = ic.model
        LEFT JOIN rerank_configs rc ON rc.workspace_id = w.id
        WHERE w.name = $1
        """,
        name,
    )
```

- [ ] **Modifier l'appel `provider_factory` dans `mcp.py:286-291`**

```python
    provider = provider_factory(
        service=ctx["service"],
        provider=ctx["provider"],
        model=ctx["model"],
        api_key=api_key,
        base_url=ctx["base_url"],
    )
```

### Étape 6 — Mettre à jour mcp_standard.py

- [ ] **Ajouter `indexer_service: str` dans `_WsCtx` (`backend/src/rag/api/mcp_standard.py:22-31`)**

```python
@dataclass(frozen=True)
class _WsCtx:
    workspace_name: str
    rag_cnx: str
    indexer_provider: str
    indexer_model: str
    indexer_service: str
    indexer_api_key_ref: str | None
    indexer_base_url: str | None
    pool_registry: Any
    resolver: Any
```

- [ ] **Modifier la query dans `_load_context` (`mcp_standard.py:187-201`)**

```python
        row = await self._config_pool.fetchrow(
            """
            SELECT w.name, w.rag_cnx,
                   k.api_key_ref,
                   ic.provider, ic.model,
                   ic.api_key_ref AS indexer_api_key_ref,
                   ic.base_url,
                   md.service
            FROM workspaces w
            JOIN workspace_api_keys k ON k.workspace_id = w.id
            JOIN indexer_configs ic ON ic.workspace_id = w.id
            JOIN model_dimensions md ON md.provider = ic.provider AND md.model = ic.model
            WHERE w.id = $1::uuid
              AND k.fingerprint = $2
              AND k.revoked_at IS NULL
              AND (k.rotated_at IS NULL OR k.rotated_at > now() - interval '72 hours')
            """,
            workspace_id,
            fingerprint,
        )
```

- [ ] **Ajouter `indexer_service` dans `_WsCtx(...)` (`mcp_standard.py:223-232`)**

```python
        return _WsCtx(
            workspace_name=str(row["name"]),
            rag_cnx=str(row["rag_cnx"]),
            indexer_provider=str(row["provider"]),
            indexer_model=str(row["model"]),
            indexer_service=str(row["service"]),
            indexer_api_key_ref=row["indexer_api_key_ref"],
            indexer_base_url=row["base_url"],
            pool_registry=self._pool_registry,
            resolver=self._resolver,
        )
```

- [ ] **Modifier l'appel `make_provider` dans `mcp_standard.py:57-62`**

```python
    provider = make_provider(
        service=ctx.indexer_service,
        provider=ctx.indexer_provider,
        model=ctx.indexer_model,
        api_key=api_key,
        base_url=ctx.indexer_base_url,
    )
```

### Étape 7 — Vérification globale

- [ ] **Lancer tous les tests unitaires**

```bash
cd backend && uv run pytest tests/unit/ -v
```

Résultat attendu : tous les tests PASS (y compris les anciens tests sur azure_openai, voyage, openai via les anciens fichiers qui existent encore).

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/indexer/providers/factory.py \
    src/rag/indexer/real.py src/rag/api/playground.py \
    src/rag/services/mcp.py src/rag/api/mcp_standard.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/indexer/providers/factory.py \
        backend/tests/unit/test_provider_factory.py \
        backend/src/rag/indexer/real.py \
        backend/src/rag/api/playground.py \
        backend/src/rag/services/mcp.py \
        backend/src/rag/api/mcp_standard.py
git commit -m "feat(indexer): factory rewrite service+platform + callers mis à jour"
```

---

## Task 12 : Supprimer les anciens fichiers provider

**Files supprimés:**
- `backend/src/rag/indexer/providers/openai.py`
- `backend/src/rag/indexer/providers/voyage.py`
- `backend/src/rag/indexer/providers/azure_openai.py`
- `backend/src/rag/indexer/providers/ollama.py`
- `backend/src/rag/indexer/providers/mistral.py`
- `backend/src/rag/indexer/providers/jina.py`
- `backend/src/rag/indexer/providers/gemini.py`
- `backend/src/rag/indexer/providers/dashscope.py`
- `backend/tests/unit/test_provider_azure_openai.py`

- [ ] **Vérifier que la suite complète est verte avant de supprimer**

```bash
cd backend && uv run pytest tests/unit/ -v --tb=short 2>&1 | tail -5
```

Résultat attendu : toutes les suites passent.

- [ ] **Supprimer les anciens fichiers**

```bash
cd backend && git rm \
    src/rag/indexer/providers/openai.py \
    src/rag/indexer/providers/voyage.py \
    src/rag/indexer/providers/azure_openai.py \
    src/rag/indexer/providers/ollama.py \
    src/rag/indexer/providers/mistral.py \
    src/rag/indexer/providers/jina.py \
    src/rag/indexer/providers/gemini.py \
    src/rag/indexer/providers/dashscope.py \
    tests/unit/test_provider_azure_openai.py
```

- [ ] **Vérifier que la suite passe toujours**

```bash
cd backend && uv run pytest tests/unit/ -v --tb=short 2>&1 | tail -5
```

Résultat attendu : toujours vert. Les anciens tests `test_provider_azure_openai.py` qui testaient `AzureOpenAIProvider` disparaissent ; leur couverture est assurée par `test_adapter.py` + `test_platform_azure_openai.py`.

- [ ] **Commit**

```bash
git commit -m "refactor(indexer): supprimer anciens providers (remplacés par adapter+service+platform)"
```

---

## Task 13 : LLM clients — azure-foundry (TDD)

**Files:**
- Modify: `backend/src/rag/services/llm_clients.py`

- [ ] **Ajouter le test**

Dans le fichier de test LLM existant, ou créer `backend/tests/unit/test_llm_clients_azure_foundry.py` :

```python
# backend/tests/unit/test_llm_clients_azure_foundry.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag.services.llm_clients import call_llm


@pytest.mark.asyncio
async def test_call_llm_azure_foundry_dispatches_to_openai_client() -> None:
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="réponse azure foundry"))]
    mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("rag.services.llm_clients.openai") as mock_openai:
        mock_openai.AsyncOpenAI.return_value = mock_client
        result = await call_llm(
            provider="azure-foundry",
            model="meta-llama-3.3-70b-instruct",
            api_key="az-key",
            base_url="https://name.region.models.ai.azure.com/v1",
            system_prompt="Tu es un assistant.",
            messages=[{"role": "user", "content": "Bonjour"}],
        )

    mock_openai.AsyncOpenAI.assert_called_once_with(
        api_key="az-key",
        base_url="https://name.region.models.ai.azure.com/v1",
    )
    assert result["answer"] == "réponse azure foundry"
    assert result["usage"]["prompt_tokens"] == 10
    assert result["usage"]["completion_tokens"] == 5


@pytest.mark.asyncio
async def test_call_llm_azure_foundry_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        await call_llm(
            provider="unknown-llm",
            model="x",
            api_key=None,
            base_url=None,
            system_prompt="",
            messages=[],
        )
```

- [ ] **Vérifier que le test échoue**

```bash
cd backend && uv run pytest tests/unit/test_llm_clients_azure_foundry.py -v 2>&1 | head -10
```

Résultat attendu : FAILED (provider `azure-foundry` non géré → `ValueError`).

- [ ] **Ajouter `_call_azure_foundry` dans `llm_clients.py`**

Dans `call_llm()`, ajouter avant la ligne `raise ValueError(...)` :

```python
    if provider == "azure-foundry":
        return await _call_azure_foundry(
            model=model,
            api_key=api_key,
            base_url=base_url,
            system=system_prompt,
            messages=messages,
        )
```

Ajouter la fonction en fin de fichier :

```python
async def _call_azure_foundry(
    *, model: str, api_key: str | None, base_url: str | None,
    system: str, messages: list[dict[str, str]]
) -> dict[str, Any]:
    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
    full_messages = [{"role": "system", "content": system}, *messages]
    response = await client.chat.completions.create(model=model, messages=full_messages)
    return {
        "answer": response.choices[0].message.content or "",
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        },
    }
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_llm_clients_azure_foundry.py -v
```

Résultat attendu : 2 tests PASS.

- [ ] **Commit**

```bash
git add backend/src/rag/services/llm_clients.py \
        backend/tests/unit/test_llm_clients_azure_foundry.py
git commit -m "feat(llm): azure-foundry LLM provider via OpenAI-compatible client"
```

---

## Task 14 : Mise à jour de specs/05-indexers.md

**Files:**
- Modify: `specs/05-indexers.md`

- [ ] **Ajouter la section Azure AI Foundry après la section Azure OpenAI**

Ajouter le bloc suivant dans `specs/05-indexers.md` :

```markdown
### Azure AI Foundry

```json
{
  "service": "voyage",
  "provider": "azure-foundry",
  "model": "voyage-4",
  "base_url": "https://{name}.{region}.models.ai.azure.com/v1",
  "api_key_ref": "azure_foundry_api_key"
}
```

| Modèle | Dimension | Service | Usage recommandé |
|---|---|---|---|
| voyage-3.5 | 1024 | voyage | Embeddings Voyage dans l'infra Azure |
| voyage-4 | 1024 | voyage | Meilleure qualité Voyage dans l'infra Azure |
| voyage-4-lite | 512 | voyage | Léger, données sensibles dans Azure |

Azure AI Foundry expose une API compatible OpenAI (`Authorization: Bearer`). Le `base_url` est l'endpoint complet du déploiement serverless Azure.

**Différence avec `azure-openai`** : azure-foundry utilise Bearer (pas `api-key`), envoie le champ `model` dans le payload, et ne nécessite pas de `api-version` dans l'URL.
```

- [ ] **Mettre à jour la table des dimensions**

Ajouter dans le tableau de référence :

```
| azure-foundry | voyage-3.5    | 1024 |
| azure-foundry | voyage-4      | 1024 |
| azure-foundry | voyage-4-lite |  512 |
```

- [ ] **Mettre à jour la table des recommandations par workspace**

Mettre à jour la ligne colis21 :

```
| colis21 | azure-foundry/voyage-4 | Données Pickup — restent dans l'infra Azure, qualité voyage |
```

- [ ] **Commit**

```bash
git add specs/05-indexers.md
git commit -m "docs(specs): azure-foundry provider embedding — voyage-3.5/4/4-lite"
```

---

## Vérification finale

- [ ] **Suite complète**

```bash
cd backend && uv run pytest tests/unit/ -v --tb=short
```

Résultat attendu : toutes les suites vertes.

- [ ] **Lint complet**

```bash
cd backend && uv run ruff check src/rag/indexer/providers/ src/rag/services/llm_clients.py
```

Résultat attendu : aucune erreur.

- [ ] **Type check**

```bash
cd frontend && npx tsc --noEmit
```

(backend only modifié — pas de changement frontend)
