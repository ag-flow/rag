# M4c — API MCP Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exposer `POST /mcp` (recherche vectorielle pgvector multi-workspace) avec auth api_key dans le body, en réutilisant `ApiKeyCache`, `WorkspacePoolRegistry`, et la table `embeddings` de M4a.

**Architecture:** Un router minimal délègue à un service `mcp.search(refs, query, top_k, min_score)` qui orchestre via `asyncio.gather` un `_search_one` par workspace : auth (cache LRU bcrypt) → load context → resolve api_key vault → `provider.embed_query(query)` → SQL pgvector (over-fetch ×4, filter Python, slice top_k). Fail-fast multi-workspace. DTO union strict `SingleWorkspaceRequest | MultiWorkspaceRequest` avec `extra="forbid"`.

**Tech Stack:** FastAPI, Pydantic v2 (union sans discriminator + smart mode), pgvector (cosine), asyncpg, `asyncio.gather`, structlog, httpx (transport mockable côté tests Voyage), pytest + httpx TestClient.

---

## File Structure

| Fichier | Statut | Responsabilité |
|---|---|---|
| `backend/src/rag/indexer/providers/protocol.py` | **Modify** | Ajouter `embed_query(text: str) -> list[float]` au Protocol |
| `backend/src/rag/indexer/providers/openai.py` | **Modify** | `embed_query` délègue à `embed_texts([text])[0]` |
| `backend/src/rag/indexer/providers/voyage.py` | **Modify** | `_embed_batch` refactor (param `input_type` keyword-only) + `embed_query` avec `input_type="query"` |
| `backend/src/rag/indexer/providers/ollama.py` | **Modify** | `embed_query` délègue à `embed_texts([text])[0]` |
| `backend/src/rag/schemas/mcp.py` | **Create** | DTOs `SingleWorkspaceRequest`, `MultiWorkspaceRequest`, `_McpWorkspaceRef`, `McpRequest` (union), `SearchHit`, `McpResponse` |
| `backend/src/rag/db/workspace_search.py` | **Create** | `vector_search(pool, query_vec, top_k, min_score, workspace_name, indexer_used) -> list[SearchHit]` |
| `backend/src/rag/services/mcp.py` | **Create** | `McpWorkspaceRef` dataclass, `normalize_refs`, `_authenticate`, `_load_workspace_context`, `_search_one`, `search` |
| `backend/src/rag/api/mcp.py` | **Create** | `build_mcp_router()` avec endpoint POST `/mcp` |
| `backend/src/rag/main.py` | **Modify** | `app.include_router(build_mcp_router())` |
| `backend/tests/unit/indexer/test_providers_embed_query.py` | **Create** | Tests unitaires `embed_query` sur les 3 providers |
| `backend/tests/unit/schemas/test_mcp_dto.py` | **Create** | Tests unitaires DTOs union + champs |
| `backend/tests/unit/services/test_mcp_normalize.py` | **Create** | Tests unitaires `normalize_refs` |
| `backend/tests/unit/db/test_workspace_search.py` | **Create** | Tests unitaires `vector_search` (over-fetch + filter Python) |
| `backend/tests/unit/services/test_mcp_search.py` | **Create** | Tests unitaires orchestration avec FakeProvider + FakePool |
| `backend/tests/api/test_mcp_single.py` | **Create** | Tests integration single workspace (DB jetable + fake provider injecté) |
| `backend/tests/api/test_mcp_multi.py` | **Create** | Tests integration multi-workspace |
| `backend/tests/api/test_mcp_errors.py` | **Create** | Tests integration codes erreurs 401/404/422 |
| `backend/tests/api/test_mcp_e2e_ollama_smoke.py` | **Create** | Smoke E2E Ollama (`@pytest.mark.smoke`, opt-in via `OLLAMA_TEST_URL`) |

---

## Task 1: `embed_query` sur OpenAIProvider

**Files:**
- Modify: `backend/src/rag/indexer/providers/protocol.py`
- Modify: `backend/src/rag/indexer/providers/openai.py`
- Create: `backend/tests/unit/indexer/__init__.py` (empty si absent)
- Create: `backend/tests/unit/indexer/test_providers_embed_query.py`

- [ ] **Step 1: Écrire le test pour OpenAI**

```python
# backend/tests/unit/indexer/test_providers_embed_query.py
from __future__ import annotations

import json

import httpx
import pytest

from rag.indexer.providers.openai import OpenAIProvider
from rag.indexer.providers.protocol import EmbeddingProviderUnreachable


def _mock_transport(json_payload: dict) -> httpx.MockTransport:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=json_payload)
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_openai_embed_query_returns_first_vector() -> None:
    transport = _mock_transport({
        "data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]
    })
    provider = OpenAIProvider(
        model="text-embedding-3-small",
        api_key="sk-test",
        transport=transport,
    )
    vec = await provider.embed_query("hello")
    assert vec == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_openai_embed_query_raises_on_empty_response() -> None:
    transport = _mock_transport({"data": []})
    provider = OpenAIProvider(
        model="text-embedding-3-small",
        api_key="sk-test",
        transport=transport,
    )
    with pytest.raises(EmbeddingProviderUnreachable, match="empty embedding"):
        await provider.embed_query("hello")
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
cd backend
uv run pytest tests/unit/indexer/test_providers_embed_query.py::test_openai_embed_query_returns_first_vector -v
```

Expected: `AttributeError: 'OpenAIProvider' object has no attribute 'embed_query'`.

- [ ] **Step 3: Ajouter `embed_query` au Protocol**

Edit `backend/src/rag/indexer/providers/protocol.py`. After the existing `embed_texts` method in `EmbeddingProvider`, add:

```python
    async def embed_query(self, text: str) -> list[float]:
        """Embed une query de recherche.

        Distinct de `embed_texts` pour permettre aux providers comme Voyage
        d'utiliser `input_type="query"` (meilleure qualité search vs document).
        Les providers sans distinction (OpenAI, Ollama) délèguent à
        `embed_texts([text])[0]`.
        """
        ...
```

- [ ] **Step 4: Implémenter `embed_query` sur OpenAIProvider**

Append to `backend/src/rag/indexer/providers/openai.py` inside the class (after `embed_texts`):

```python
    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        if not vectors:
            raise EmbeddingProviderUnreachable("OpenAI returned empty embedding")
        return vectors[0]
```

- [ ] **Step 5: Run tests to verify they pass**

```powershell
uv run pytest tests/unit/indexer/test_providers_embed_query.py -v
```

Expected: `2 passed`.

- [ ] **Step 6: Commit**

```powershell
git add backend/src/rag/indexer/providers/protocol.py backend/src/rag/indexer/providers/openai.py backend/tests/unit/indexer/__init__.py backend/tests/unit/indexer/test_providers_embed_query.py
git commit -m "feat(M4c): embed_query sur EmbeddingProvider + OpenAI"
```

---

## Task 2: `embed_query` sur VoyageProvider (input_type="query")

**Files:**
- Modify: `backend/src/rag/indexer/providers/voyage.py`
- Modify: `backend/tests/unit/indexer/test_providers_embed_query.py` (ajout tests Voyage)

- [ ] **Step 1: Écrire les tests Voyage**

Append to `backend/tests/unit/indexer/test_providers_embed_query.py`:

```python
import json as _json  # ajouter en haut du fichier si pas déjà importé

from rag.indexer.providers.voyage import VoyageProvider


@pytest.mark.asyncio
async def test_voyage_embed_query_sends_input_type_query() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = _json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={
            "data": [{"index": 0, "embedding": [0.5, 0.6]}]
        })

    transport = httpx.MockTransport(handler)
    provider = VoyageProvider(
        model="voyage-3-lite",
        api_key="vk-test",
        transport=transport,
    )
    vec = await provider.embed_query("ma question")

    assert vec == [0.5, 0.6]
    assert captured["body"]["input"] == ["ma question"]
    assert captured["body"]["input_type"] == "query"
    assert captured["body"]["model"] == "voyage-3-lite"


@pytest.mark.asyncio
async def test_voyage_embed_texts_still_uses_input_type_document() -> None:
    """Régression : embed_texts garde input_type=document."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = _json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={
            "data": [{"index": 0, "embedding": [0.1, 0.2]}]
        })

    transport = httpx.MockTransport(handler)
    provider = VoyageProvider(
        model="voyage-3-lite",
        api_key="vk-test",
        transport=transport,
    )
    await provider.embed_texts(["du contenu"])
    assert captured["body"]["input_type"] == "document"
```

- [ ] **Step 2: Run tests to verify the new ones fail**

```powershell
uv run pytest tests/unit/indexer/test_providers_embed_query.py::test_voyage_embed_query_sends_input_type_query -v
```

Expected: `AttributeError: 'VoyageProvider' object has no attribute 'embed_query'`.

- [ ] **Step 3: Refactor `_embed_batch` pour accepter `input_type` keyword**

Edit `backend/src/rag/indexer/providers/voyage.py`. Change the signature of `_embed_batch`:

```python
    async def _embed_batch(
        self,
        client: httpx.AsyncClient,
        batch: list[str],
        *,
        input_type: str = "document",
    ) -> list[list[float]]:
```

And update the line that builds the JSON body to use the parameter:

```python
                response = await client.post(
                    _VOYAGE_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": self._model,
                        "input": batch,
                        "input_type": input_type,
                    },
                )
```

- [ ] **Step 4: Implémenter `embed_query` sur VoyageProvider**

Append inside the `VoyageProvider` class (after `embed_texts`):

```python
    async def embed_query(self, text: str) -> list[float]:
        if not self._api_key:
            raise EmbeddingAuthError("Voyage api_key is required (got None)")
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=_TIMEOUT_SECONDS,
        ) as client:
            batch_result = await self._embed_batch(client, [text], input_type="query")
        if not batch_result:
            raise EmbeddingProviderUnreachable("Voyage returned empty embedding")
        return batch_result[0]
```

- [ ] **Step 5: Run tests to verify they pass**

```powershell
uv run pytest tests/unit/indexer/test_providers_embed_query.py -v
```

Expected: `4 passed` (2 OpenAI + 2 Voyage). Verify the regression test confirms `embed_texts` still uses `input_type="document"`.

- [ ] **Step 6: Run full voyage test suite to catch any regression**

```powershell
uv run pytest tests/unit/indexer/ -v -k voyage
```

Expected: tous les tests Voyage existants passent (incluant les tests M4a).

- [ ] **Step 7: Commit**

```powershell
git add backend/src/rag/indexer/providers/voyage.py backend/tests/unit/indexer/test_providers_embed_query.py
git commit -m "feat(M4c): embed_query sur Voyage avec input_type=query"
```

---

## Task 3: `embed_query` sur OllamaProvider

**Files:**
- Modify: `backend/src/rag/indexer/providers/ollama.py`
- Modify: `backend/tests/unit/indexer/test_providers_embed_query.py` (ajout tests Ollama)

- [ ] **Step 1: Écrire les tests Ollama**

Append to `backend/tests/unit/indexer/test_providers_embed_query.py`:

```python
from rag.indexer.providers.ollama import OllamaProvider


@pytest.mark.asyncio
async def test_ollama_embed_query_returns_first_vector() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embedding": [0.7, 0.8, 0.9]})

    transport = httpx.MockTransport(handler)
    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://fake:11434",
        transport=transport,
    )
    vec = await provider.embed_query("requête test")
    assert vec == [0.7, 0.8, 0.9]


@pytest.mark.asyncio
async def test_ollama_embed_query_raises_on_empty_response() -> None:
    """Ollama embed_texts retourne [] si list vide en entrée — embed_query
    appelle avec [text] donc ne devrait jamais retourner []. Test défensif."""
    # Mock un retour OK mais vérifie le chemin d'erreur si quelque chose
    # tournait mal côté embed_texts. Pratique : skip ce test si pas pertinent
    # parce que `embed_texts(["x"])` retourne toujours [vec] ou raise.


@pytest.mark.asyncio
async def test_ollama_embed_query_delegates_to_embed_texts() -> None:
    """Vérifie qu'on appelle bien l'API Ollama 1× avec [text]."""
    call_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"embedding": [0.1]})

    transport = httpx.MockTransport(handler)
    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://fake:11434",
        transport=transport,
    )
    await provider.embed_query("x")
    assert call_count == 1
```

Note : on retire le test `test_ollama_embed_query_raises_on_empty_response` (faux problème — `embed_texts([text])` retourne toujours `[vec]` ou raise) et on garde les 2 utiles.

```python
# Version finale de la partie Ollama ajoutée au fichier :
from rag.indexer.providers.ollama import OllamaProvider


@pytest.mark.asyncio
async def test_ollama_embed_query_returns_first_vector() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embedding": [0.7, 0.8, 0.9]})

    transport = httpx.MockTransport(handler)
    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://fake:11434",
        transport=transport,
    )
    vec = await provider.embed_query("requête test")
    assert vec == [0.7, 0.8, 0.9]


@pytest.mark.asyncio
async def test_ollama_embed_query_delegates_single_call() -> None:
    call_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"embedding": [0.1]})

    transport = httpx.MockTransport(handler)
    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://fake:11434",
        transport=transport,
    )
    await provider.embed_query("x")
    assert call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
uv run pytest tests/unit/indexer/test_providers_embed_query.py::test_ollama_embed_query_returns_first_vector -v
```

Expected: `AttributeError: 'OllamaProvider' object has no attribute 'embed_query'`.

- [ ] **Step 3: Implémenter `embed_query` sur OllamaProvider**

Append inside `OllamaProvider` class (after `embed_texts`):

```python
    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        if not vectors:
            raise EmbeddingProviderUnreachable("Ollama returned empty embedding")
        return vectors[0]
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
uv run pytest tests/unit/indexer/test_providers_embed_query.py -v
```

Expected: `6 passed` (2 OpenAI + 2 Voyage + 2 Ollama).

- [ ] **Step 5: Lint/format/mypy**

```powershell
uv run ruff check src/rag/indexer/providers/ tests/unit/indexer/
uv run ruff format src/rag/indexer/providers/ tests/unit/indexer/
uv run mypy src/rag/indexer/providers/
```

- [ ] **Step 6: Commit**

```powershell
git add backend/src/rag/indexer/providers/ollama.py backend/tests/unit/indexer/test_providers_embed_query.py
git commit -m "feat(M4c): embed_query sur Ollama"
```

---

## Task 4: Schemas DTOs (union strict)

**Files:**
- Create: `backend/src/rag/schemas/mcp.py`
- Create: `backend/tests/unit/schemas/test_mcp_dto.py`

- [ ] **Step 1: Écrire les tests DTOs**

```python
# backend/tests/unit/schemas/test_mcp_dto.py
from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from rag.schemas.mcp import (
    McpRequest,
    MultiWorkspaceRequest,
    SearchHit,
    SingleWorkspaceRequest,
)

_ADAPTER = TypeAdapter(McpRequest)


def test_single_request_accepts_minimal_payload() -> None:
    req = SingleWorkspaceRequest(
        workspace="harpocrate",
        api_key="ws_key_xyz",
        query="comment ça marche ?",
    )
    assert req.workspace == "harpocrate"
    assert req.top_k == 5  # default
    assert req.min_score == 0.7  # default


def test_multi_request_accepts_workspaces_list() -> None:
    req = MultiWorkspaceRequest(
        workspaces=[
            {"name": "ws_a", "api_key": "k1"},
            {"name": "ws_b", "api_key": "k2"},
        ],
        query="hello",
    )
    assert len(req.workspaces) == 2
    assert req.workspaces[0].name == "ws_a"


def test_union_dispatches_single_when_workspace_field_present() -> None:
    obj = _ADAPTER.validate_python({
        "workspace": "ws",
        "api_key": "k",
        "query": "q",
    })
    assert isinstance(obj, SingleWorkspaceRequest)


def test_union_dispatches_multi_when_workspaces_field_present() -> None:
    obj = _ADAPTER.validate_python({
        "workspaces": [{"name": "ws", "api_key": "k"}],
        "query": "q",
    })
    assert isinstance(obj, MultiWorkspaceRequest)


def test_union_rejects_mix_of_single_and_multi() -> None:
    with pytest.raises(ValidationError):
        _ADAPTER.validate_python({
            "workspace": "ws",
            "api_key": "k",
            "workspaces": [{"name": "ws", "api_key": "k"}],
            "query": "q",
        })


def test_single_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        SingleWorkspaceRequest(workspace="ws", api_key="k", query="")


def test_single_rejects_query_above_2000_chars() -> None:
    with pytest.raises(ValidationError):
        SingleWorkspaceRequest(
            workspace="ws",
            api_key="k",
            query="a" * 2001,
        )


def test_single_rejects_top_k_zero() -> None:
    with pytest.raises(ValidationError):
        SingleWorkspaceRequest(workspace="ws", api_key="k", query="q", top_k=0)


def test_single_rejects_top_k_above_50() -> None:
    with pytest.raises(ValidationError):
        SingleWorkspaceRequest(workspace="ws", api_key="k", query="q", top_k=51)


def test_single_rejects_min_score_above_one() -> None:
    with pytest.raises(ValidationError):
        SingleWorkspaceRequest(
            workspace="ws", api_key="k", query="q", min_score=1.1,
        )


def test_single_rejects_min_score_below_minus_one() -> None:
    with pytest.raises(ValidationError):
        SingleWorkspaceRequest(
            workspace="ws", api_key="k", query="q", min_score=-1.1,
        )


def test_multi_rejects_empty_workspaces_list() -> None:
    with pytest.raises(ValidationError):
        MultiWorkspaceRequest(workspaces=[], query="q")


def test_multi_rejects_more_than_10_workspaces() -> None:
    with pytest.raises(ValidationError):
        MultiWorkspaceRequest(
            workspaces=[
                {"name": f"ws_{i}", "api_key": "k"} for i in range(11)
            ],
            query="q",
        )


def test_single_rejects_invalid_workspace_name() -> None:
    with pytest.raises(ValidationError):
        SingleWorkspaceRequest(
            workspace="Invalid Name",  # uppercase + space
            api_key="k",
            query="q",
        )


def test_search_hit_serializes_full_payload() -> None:
    hit = SearchHit(
        workspace="ws",
        indexer="openai/text-embedding-3-small",
        path="docs/foo.md",
        chunk_index=2,
        content="extrait",
        score=0.91,
    )
    d = hit.model_dump()
    assert d["workspace"] == "ws"
    assert d["indexer"] == "openai/text-embedding-3-small"
    assert d["score"] == 0.91
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
uv run pytest tests/unit/schemas/test_mcp_dto.py -v
```

Expected: `ModuleNotFoundError: No module named 'rag.schemas.mcp'`.

- [ ] **Step 3: Créer `schemas/mcp.py`**

```python
# backend/src/rag/schemas/mcp.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_QUERY_MAX_LEN = 2000
_TOP_K_MAX = 50
_API_KEY_MAX = 128
_WORKSPACE_NAME_REGEX = r"^[a-z][a-z0-9_-]{0,62}$"


class _McpRequestBase(BaseModel):
    """Champs communs single+multi. `extra="forbid"` rejette un payload
    qui mixe `workspace` + `workspaces` (sinon le champ "en trop" passerait
    silencieusement dans l'un des variants)."""
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=_QUERY_MAX_LEN)
    top_k: int = Field(default=5, ge=1, le=_TOP_K_MAX)
    min_score: float = Field(default=0.7, ge=-1.0, le=1.0)


class SingleWorkspaceRequest(_McpRequestBase):
    workspace: str = Field(..., pattern=_WORKSPACE_NAME_REGEX)
    api_key: str = Field(..., min_length=1, max_length=_API_KEY_MAX)


class _McpWorkspaceRef(BaseModel):
    """Item de la liste `workspaces` côté MultiWorkspaceRequest."""
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., pattern=_WORKSPACE_NAME_REGEX)
    api_key: str = Field(..., min_length=1, max_length=_API_KEY_MAX)


class MultiWorkspaceRequest(_McpRequestBase):
    workspaces: list[_McpWorkspaceRef] = Field(..., min_length=1, max_length=10)


# Union Pydantic v2 smart-mode : tente Single puis Multi (ou l'inverse) et
# garde le variant qui matche le mieux. `extra="forbid"` garantit qu'un
# payload mixte ne matche aucun.
McpRequest = SingleWorkspaceRequest | MultiWorkspaceRequest


class SearchHit(BaseModel):
    workspace: str
    indexer: str
    path: str
    chunk_index: int
    content: str
    score: float


class McpResponse(BaseModel):
    query: str
    results: list[SearchHit]
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
uv run pytest tests/unit/schemas/test_mcp_dto.py -v
```

Expected: `15 passed`.

- [ ] **Step 5: Lint/format/mypy**

```powershell
uv run ruff check src/rag/schemas/mcp.py tests/unit/schemas/test_mcp_dto.py
uv run ruff format src/rag/schemas/mcp.py tests/unit/schemas/test_mcp_dto.py
uv run mypy src/rag/schemas/mcp.py
```

- [ ] **Step 6: Commit**

```powershell
git add backend/src/rag/schemas/mcp.py backend/tests/unit/schemas/test_mcp_dto.py
git commit -m "feat(M4c): schemas DTOs McpRequest union + SearchHit"
```

---

## Task 5: `normalize_refs` + `McpWorkspaceRef` dataclass

**Files:**
- Create: `backend/src/rag/services/mcp.py` (partial — pour cette task uniquement la dataclass + `normalize_refs`)
- Create: `backend/tests/unit/services/test_mcp_normalize.py`

- [ ] **Step 1: Écrire les tests**

```python
# backend/tests/unit/services/test_mcp_normalize.py
from __future__ import annotations

from rag.schemas.mcp import MultiWorkspaceRequest, SingleWorkspaceRequest
from rag.services.mcp import McpWorkspaceRef, normalize_refs


def test_normalize_single_returns_one_ref() -> None:
    req = SingleWorkspaceRequest(workspace="ws_a", api_key="k1", query="q")
    refs = normalize_refs(req)
    assert refs == [McpWorkspaceRef(name="ws_a", api_key="k1")]


def test_normalize_multi_preserves_order_and_size() -> None:
    req = MultiWorkspaceRequest(
        workspaces=[
            {"name": "ws_a", "api_key": "k1"},
            {"name": "ws_b", "api_key": "k2"},
            {"name": "ws_c", "api_key": "k3"},
        ],
        query="q",
    )
    refs = normalize_refs(req)
    assert refs == [
        McpWorkspaceRef(name="ws_a", api_key="k1"),
        McpWorkspaceRef(name="ws_b", api_key="k2"),
        McpWorkspaceRef(name="ws_c", api_key="k3"),
    ]


def test_mcp_workspace_ref_is_frozen() -> None:
    """frozen dataclass empêche un service d'altérer la ref par accident."""
    import dataclasses
    ref = McpWorkspaceRef(name="ws", api_key="k")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ref.name = "other"  # type: ignore[misc]


# pytest import requis pour le frozen test
import pytest  # noqa: E402
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
uv run pytest tests/unit/services/test_mcp_normalize.py -v
```

Expected: `ModuleNotFoundError: No module named 'rag.services.mcp'`.

- [ ] **Step 3: Créer `services/mcp.py` avec `McpWorkspaceRef` + `normalize_refs`**

```python
# backend/src/rag/services/mcp.py
from __future__ import annotations

from dataclasses import dataclass

from rag.schemas.mcp import MultiWorkspaceRequest, SingleWorkspaceRequest


@dataclass(frozen=True)
class McpWorkspaceRef:
    """Représentation interne d'un workspace+api_key à interroger.

    `frozen=True` : empêche `_search_one` ou `_authenticate` de muter
    accidentellement la ref entre tâches asyncio.gather concurrentes.
    """
    name: str
    api_key: str


def normalize_refs(
    req: SingleWorkspaceRequest | MultiWorkspaceRequest,
) -> list[McpWorkspaceRef]:
    """Convertit le DTO d'entrée en liste interne (ordre préservé)."""
    if isinstance(req, SingleWorkspaceRequest):
        return [McpWorkspaceRef(name=req.workspace, api_key=req.api_key)]
    return [McpWorkspaceRef(name=w.name, api_key=w.api_key) for w in req.workspaces]
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
uv run pytest tests/unit/services/test_mcp_normalize.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/rag/services/mcp.py backend/tests/unit/services/test_mcp_normalize.py
git commit -m "feat(M4c): normalize_refs + McpWorkspaceRef dataclass"
```

---

## Task 6: `vector_search` SQL helper

**Files:**
- Create: `backend/src/rag/db/workspace_search.py`
- Create: `backend/tests/unit/db/__init__.py` (empty si absent)
- Create: `backend/tests/unit/db/test_workspace_search.py`

- [ ] **Step 1: Écrire les tests unitaires (mock asyncpg)**

```python
# backend/tests/unit/db/test_workspace_search.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.db.workspace_search import vector_search


def _make_pool_returning(rows: list[dict]) -> MagicMock:
    """Fake asyncpg.Pool avec acquire()→connection qui retourne `rows`."""
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


@pytest.mark.asyncio
async def test_vector_search_overfetches_4x_top_k(monkeypatch) -> None:
    """vector_search doit demander LIMIT $2 = top_k * 4 à pgvector."""
    from rag.db import workspace_search
    monkeypatch.setattr(workspace_search, "register_vector", AsyncMock())

    rows: list[dict] = []
    pool = _make_pool_returning(rows)

    await vector_search(
        pool,
        query_vec=[0.1, 0.2],
        top_k=5,
        min_score=0.0,
        workspace_name="ws",
        indexer_used="openai/m",
    )

    conn = pool.acquire.return_value.__aenter__.return_value
    # 2e arg de conn.fetch = LIMIT
    args = conn.fetch.call_args[0]
    assert args[2] == 5 * 4  # over-fetch


@pytest.mark.asyncio
async def test_vector_search_filters_below_min_score(monkeypatch) -> None:
    from rag.db import workspace_search
    monkeypatch.setattr(workspace_search, "register_vector", AsyncMock())

    rows = [
        {"path": "a.md", "chunk_index": 0, "content": "hi", "score": 0.95},
        {"path": "b.md", "chunk_index": 0, "content": "lo", "score": 0.50},
        {"path": "c.md", "chunk_index": 0, "content": "mid", "score": 0.80},
    ]
    pool = _make_pool_returning(rows)

    hits = await vector_search(
        pool,
        query_vec=[0.1],
        top_k=10,
        min_score=0.7,
        workspace_name="ws",
        indexer_used="openai/m",
    )
    assert [h.path for h in hits] == ["a.md", "c.md"]
    assert all(h.score >= 0.7 for h in hits)


@pytest.mark.asyncio
async def test_vector_search_slices_to_top_k_after_filter(monkeypatch) -> None:
    from rag.db import workspace_search
    monkeypatch.setattr(workspace_search, "register_vector", AsyncMock())

    rows = [
        {"path": f"p{i}.md", "chunk_index": 0, "content": "x", "score": 0.9 - i * 0.01}
        for i in range(10)
    ]
    pool = _make_pool_returning(rows)

    hits = await vector_search(
        pool,
        query_vec=[0.1],
        top_k=3,
        min_score=0.0,
        workspace_name="ws",
        indexer_used="openai/m",
    )
    assert len(hits) == 3
    assert [h.path for h in hits] == ["p0.md", "p1.md", "p2.md"]


@pytest.mark.asyncio
async def test_vector_search_returns_search_hit_with_workspace_and_indexer(monkeypatch) -> None:
    from rag.db import workspace_search
    monkeypatch.setattr(workspace_search, "register_vector", AsyncMock())

    rows = [{"path": "x.md", "chunk_index": 7, "content": "blob", "score": 0.88}]
    pool = _make_pool_returning(rows)

    hits = await vector_search(
        pool,
        query_vec=[0.1],
        top_k=5,
        min_score=0.0,
        workspace_name="ws_test",
        indexer_used="voyage/voyage-3-lite",
    )
    assert len(hits) == 1
    h = hits[0]
    assert h.workspace == "ws_test"
    assert h.indexer == "voyage/voyage-3-lite"
    assert h.path == "x.md"
    assert h.chunk_index == 7
    assert h.content == "blob"
    assert h.score == 0.88


@pytest.mark.asyncio
async def test_vector_search_empty_rows_returns_empty(monkeypatch) -> None:
    from rag.db import workspace_search
    monkeypatch.setattr(workspace_search, "register_vector", AsyncMock())

    pool = _make_pool_returning([])
    hits = await vector_search(
        pool,
        query_vec=[0.1],
        top_k=5,
        min_score=0.0,
        workspace_name="ws",
        indexer_used="openai/m",
    )
    assert hits == []
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
uv run pytest tests/unit/db/test_workspace_search.py -v
```

Expected: `ModuleNotFoundError: No module named 'rag.db.workspace_search'`.

- [ ] **Step 3: Créer `db/workspace_search.py`**

```python
# backend/src/rag/db/workspace_search.py
from __future__ import annotations

import asyncpg
import structlog
from pgvector.asyncpg import register_vector

from rag.schemas.mcp import SearchHit

log = structlog.get_logger(__name__)


async def vector_search(
    workspace_pool: asyncpg.Pool,
    *,
    query_vec: list[float],
    top_k: int,
    min_score: float,
    workspace_name: str,
    indexer_used: str,
) -> list[SearchHit]:
    """Top-k chunks pgvector avec score cosine >= min_score.

    Stratégie : over-fetch `top_k * 4` triés par distance ivfflat (utilise
    l'index), filtre `score >= min_score` en Python, slice `top_k`.
    Pourquoi over-fetch : un `WHERE distance < threshold` AVANT le LIMIT
    désactive l'index ivfflat. On filtre après la lecture.
    """
    async with workspace_pool.acquire() as conn:
        await register_vector(conn)
        rows = await conn.fetch(
            """
            SELECT path, chunk_index, content,
                   1 - (embedding <=> $1::vector) AS score
            FROM embeddings
            ORDER BY embedding <=> $1::vector
            LIMIT $2
            """,
            query_vec,
            top_k * 4,
        )

    hits = [
        SearchHit(
            workspace=workspace_name,
            indexer=indexer_used,
            path=r["path"],
            chunk_index=r["chunk_index"],
            content=r["content"],
            score=float(r["score"]),
        )
        for r in rows
        if float(r["score"]) >= min_score
    ]
    return hits[:top_k]
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
uv run pytest tests/unit/db/test_workspace_search.py -v
```

Expected: `5 passed`.

- [ ] **Step 5: Lint/format/mypy**

```powershell
uv run ruff check src/rag/db/workspace_search.py tests/unit/db/test_workspace_search.py
uv run ruff format src/rag/db/workspace_search.py tests/unit/db/test_workspace_search.py
uv run mypy src/rag/db/workspace_search.py
```

- [ ] **Step 6: Commit**

```powershell
git add backend/src/rag/db/workspace_search.py backend/tests/unit/db/__init__.py backend/tests/unit/db/test_workspace_search.py
git commit -m "feat(M4c): vector_search pgvector over-fetch + filter Python"
```

---

## Task 7: `_authenticate` + `_load_workspace_context`

**Files:**
- Modify: `backend/src/rag/services/mcp.py`
- Modify: `backend/tests/unit/services/test_mcp_normalize.py` (renommer ou créer un nouveau fichier dédié auth)

Note : on crée un nouveau fichier dédié `test_mcp_auth.py` pour ne pas mélanger les tests `normalize` et `auth`.

- [ ] **Step 1: Créer `backend/tests/unit/services/test_mcp_auth.py`**

```python
# backend/tests/unit/services/test_mcp_auth.py
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from rag.api.errors import WorkspaceNotFound
from rag.auth.workspace_auth import ApiKeyCache, _CacheEntry
from rag.services.mcp import McpWorkspaceRef, _authenticate, _load_workspace_context


@pytest.mark.asyncio
async def test_authenticate_cache_hit_skips_db() -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    ws_id = uuid4()
    cache.put("ws", "key", _CacheEntry(
        workspace_id=ws_id,
        indexer_used="openai/m",
        inserted_at=time.monotonic(),
    ))
    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=AssertionError("DB not allowed on cache hit"))

    ref = McpWorkspaceRef(name="ws", api_key="key")
    entry = await _authenticate(ref=ref, config_pool=pool, apikey_cache=cache)
    assert entry.workspace_id == ws_id
    assert entry.indexer_used == "openai/m"


@pytest.mark.asyncio
async def test_authenticate_workspace_not_found_raises_404() -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)

    ref = McpWorkspaceRef(name="ghost", api_key="x")
    with pytest.raises(WorkspaceNotFound):
        await _authenticate(ref=ref, config_pool=pool, apikey_cache=cache)


@pytest.mark.asyncio
async def test_authenticate_bad_bcrypt_raises_401(monkeypatch) -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    ws_id = uuid4()
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={
        "id": ws_id,
        "api_key_hash": "$2b$12$invalid",
        "indexer_used": "openai/m",
    })

    from rag.services import mcp
    monkeypatch.setattr(mcp, "verify_api_key", lambda _k, _h: False)

    ref = McpWorkspaceRef(name="ws", api_key="wrong")
    with pytest.raises(HTTPException) as exc:
        await _authenticate(ref=ref, config_pool=pool, apikey_cache=cache)
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_workspace_apikey"
    # Bad key NOT cached
    assert cache.get("ws", "wrong") is None


@pytest.mark.asyncio
async def test_authenticate_valid_bcrypt_populates_cache(monkeypatch) -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    ws_id = uuid4()
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={
        "id": ws_id,
        "api_key_hash": "$2b$12$valid",
        "indexer_used": "voyage/voyage-3-lite",
    })

    from rag.services import mcp
    monkeypatch.setattr(mcp, "verify_api_key", lambda _k, _h: True)

    ref = McpWorkspaceRef(name="ws", api_key="good")
    entry = await _authenticate(ref=ref, config_pool=pool, apikey_cache=cache)
    assert entry.workspace_id == ws_id
    assert entry.indexer_used == "voyage/voyage-3-lite"
    cached = cache.get("ws", "good")
    assert cached is not None
    assert cached.workspace_id == ws_id


@pytest.mark.asyncio
async def test_load_workspace_context_returns_full_row() -> None:
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={
        "workspace_name": "ws",
        "rag_cnx": "postgresql://...",
        "provider": "openai",
        "model": "text-embedding-3-small",
        "api_key_ref": "openai_embedding_key",
        "base_url": None,
    })
    ctx = await _load_workspace_context(pool, "ws")
    assert ctx["workspace_name"] == "ws"
    assert ctx["provider"] == "openai"
    assert ctx["api_key_ref"] == "openai_embedding_key"


@pytest.mark.asyncio
async def test_load_workspace_context_missing_workspace_raises_runtime() -> None:
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    with pytest.raises(RuntimeError):
        await _load_workspace_context(pool, "ghost")
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
uv run pytest tests/unit/services/test_mcp_auth.py -v
```

Expected: `ImportError` on `_authenticate` and `_load_workspace_context`.

- [ ] **Step 3: Étendre `services/mcp.py` avec `_authenticate` et `_load_workspace_context`**

Append to `backend/src/rag/services/mcp.py`:

```python
import time
from typing import Any

import asyncpg
from fastapi import HTTPException, status

from rag.api.errors import WorkspaceNotFound
from rag.auth.workspace_auth import ApiKeyCache, _CacheEntry
from rag.services.apikey import verify_api_key


async def _authenticate(
    *,
    ref: McpWorkspaceRef,
    config_pool: asyncpg.Pool,
    apikey_cache: ApiKeyCache,
) -> _CacheEntry:
    """Valide la pair (workspace_name, api_key) avec cache LRU+TTL.

    Returns un `_CacheEntry` (workspace_id, indexer_used, inserted_at).
    - WorkspaceNotFound si workspace inconnu ou pas d'indexer_config.
    - HTTPException 401 si bcrypt verify fails.
    """
    cached = apikey_cache.get(ref.name, ref.api_key)
    if cached is not None:
        return cached

    row = await config_pool.fetchrow(
        """
        SELECT w.id, w.api_key_hash,
               ic.provider || '/' || ic.model AS indexer_used
        FROM workspaces w
        JOIN indexer_configs ic ON ic.workspace_id = w.id
        WHERE w.name = $1
        """,
        ref.name,
    )
    if row is None:
        raise WorkspaceNotFound(ref.name)

    if not verify_api_key(ref.api_key, row["api_key_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_workspace_apikey",
        )

    entry = _CacheEntry(
        workspace_id=row["id"],
        indexer_used=row["indexer_used"],
        inserted_at=time.monotonic(),
    )
    apikey_cache.put(ref.name, ref.api_key, entry)
    return entry


async def _load_workspace_context(
    config_pool: asyncpg.Pool,
    name: str,
) -> dict[str, Any]:
    """Charge provider+model+api_key_ref+base_url+rag_cnx pour un workspace.

    Lève RuntimeError si workspace inexistant — `_authenticate` est censé
    avoir validé l'existence avant cet appel ; un None ici trahit une
    corruption d'état entre les deux SELECT.
    """
    row = await config_pool.fetchrow(
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
        WHERE w.name = $1
        """,
        name,
    )
    if row is None:
        raise RuntimeError(f"workspace {name!r} disappeared between auth and load")
    return dict(row)
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
uv run pytest tests/unit/services/test_mcp_auth.py -v
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/rag/services/mcp.py backend/tests/unit/services/test_mcp_auth.py
git commit -m "feat(M4c): _authenticate + _load_workspace_context"
```

---

## Task 8: `_search_one` + `search` orchestrator

**Files:**
- Modify: `backend/src/rag/services/mcp.py`
- Create: `backend/tests/unit/services/test_mcp_search.py`

- [ ] **Step 1: Écrire les tests d'orchestration**

```python
# backend/tests/unit/services/test_mcp_search.py
from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from rag.api.errors import WorkspaceNotFound
from rag.auth.workspace_auth import ApiKeyCache, _CacheEntry
from rag.schemas.mcp import SearchHit
from rag.services.mcp import McpWorkspaceRef, search


class _FakeProvider:
    def __init__(self, vec: list[float]) -> None:
        self._vec = vec
        self.calls = 0

    async def embed_query(self, _text: str) -> list[float]:
        self.calls += 1
        return self._vec

    async def embed_texts(self, _texts: list[str]) -> list[list[float]]:
        raise AssertionError("embed_texts not expected in search path")


class _FakeResolver:
    def __init__(self) -> None:
        self.calls = 0

    def resolve_with_retry(self, _ref: str) -> str:
        self.calls += 1
        return "resolved-secret"


def _seeded_cache(name: str, api_key: str, workspace_id, indexer_used: str) -> ApiKeyCache:
    cache = ApiKeyCache(max_size=8, ttl_seconds=60)
    cache.put(name, api_key, _CacheEntry(
        workspace_id=workspace_id,
        indexer_used=indexer_used,
        inserted_at=time.monotonic(),
    ))
    return cache


def _fake_pool_with_ctx(ctx_rows: dict[str, dict[str, Any]]) -> MagicMock:
    """pool.fetchrow renvoie le contexte par workspace name (param $1)."""
    async def _fetchrow(_query: str, name: str) -> dict[str, Any] | None:
        return ctx_rows.get(name)
    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=_fetchrow)
    return pool


def _fake_registry_returning(ws_pool: MagicMock) -> MagicMock:
    reg = MagicMock()
    reg.get_workspace_pool = AsyncMock(return_value=ws_pool)
    return reg


@pytest.mark.asyncio
async def test_search_single_workspace_returns_hits(monkeypatch) -> None:
    ws_id = uuid4()
    cache = _seeded_cache("ws_a", "k1", ws_id, "openai/text-embedding-3-small")
    pool = _fake_pool_with_ctx({
        "ws_a": {
            "workspace_name": "ws_a", "rag_cnx": "dsn",
            "provider": "openai", "model": "text-embedding-3-small",
            "api_key_ref": "openai_key", "base_url": None,
        },
    })
    ws_pool = MagicMock()
    registry = _fake_registry_returning(ws_pool)
    provider = _FakeProvider(vec=[0.1, 0.2])

    fake_vector_search = AsyncMock(return_value=[
        SearchHit(
            workspace="ws_a",
            indexer="openai/text-embedding-3-small",
            path="a.md", chunk_index=0, content="x", score=0.9,
        ),
    ])

    from rag.services import mcp
    monkeypatch.setattr(mcp, "vector_search", fake_vector_search)

    resolver = _FakeResolver()
    hits = await search(
        refs=[McpWorkspaceRef(name="ws_a", api_key="k1")],
        query="hello",
        top_k=5,
        min_score=0.7,
        config_pool=pool,
        pool_registry=registry,
        apikey_cache=cache,
        secret_resolver=resolver,
        provider_factory=lambda **_kw: provider,  # type: ignore[arg-type]
    )

    assert len(hits) == 1
    assert hits[0].workspace == "ws_a"
    assert provider.calls == 1
    assert resolver.calls == 1  # api_key_ref non-None → vault resolved


@pytest.mark.asyncio
async def test_search_skips_vault_when_api_key_ref_is_none(monkeypatch) -> None:
    ws_id = uuid4()
    cache = _seeded_cache("ws_ollama", "k1", ws_id, "ollama/nomic-embed-text")
    pool = _fake_pool_with_ctx({
        "ws_ollama": {
            "workspace_name": "ws_ollama", "rag_cnx": "dsn",
            "provider": "ollama", "model": "nomic-embed-text",
            "api_key_ref": None, "base_url": "http://ollama:11434",
        },
    })
    ws_pool = MagicMock()
    registry = _fake_registry_returning(ws_pool)
    provider = _FakeProvider(vec=[0.1])

    from rag.services import mcp
    monkeypatch.setattr(mcp, "vector_search", AsyncMock(return_value=[]))

    resolver = _FakeResolver()
    await search(
        refs=[McpWorkspaceRef(name="ws_ollama", api_key="k1")],
        query="x",
        top_k=5,
        min_score=0.7,
        config_pool=pool,
        pool_registry=registry,
        apikey_cache=cache,
        secret_resolver=resolver,
        provider_factory=lambda **_kw: provider,  # type: ignore[arg-type]
    )
    assert resolver.calls == 0  # api_key_ref None → no vault call


@pytest.mark.asyncio
async def test_search_multi_workspace_concat_in_order(monkeypatch) -> None:
    cache = ApiKeyCache(max_size=8, ttl_seconds=60)
    cache.put("ws_a", "k1", _CacheEntry(
        workspace_id=uuid4(), indexer_used="openai/m", inserted_at=time.monotonic(),
    ))
    cache.put("ws_b", "k2", _CacheEntry(
        workspace_id=uuid4(), indexer_used="voyage/m", inserted_at=time.monotonic(),
    ))

    pool = _fake_pool_with_ctx({
        "ws_a": {
            "workspace_name": "ws_a", "rag_cnx": "dsn_a",
            "provider": "openai", "model": "m",
            "api_key_ref": None, "base_url": None,
        },
        "ws_b": {
            "workspace_name": "ws_b", "rag_cnx": "dsn_b",
            "provider": "voyage", "model": "m",
            "api_key_ref": None, "base_url": None,
        },
    })
    ws_pool = MagicMock()
    registry = _fake_registry_returning(ws_pool)
    provider = _FakeProvider(vec=[0.1])

    async def _vector_search(_pool, **kw: Any) -> list[SearchHit]:
        name = kw["workspace_name"]
        return [SearchHit(
            workspace=name,
            indexer=kw["indexer_used"],
            path=f"{name}.md", chunk_index=0, content="x", score=0.9,
        )]

    from rag.services import mcp
    monkeypatch.setattr(mcp, "vector_search", _vector_search)

    hits = await search(
        refs=[
            McpWorkspaceRef(name="ws_a", api_key="k1"),
            McpWorkspaceRef(name="ws_b", api_key="k2"),
        ],
        query="x", top_k=5, min_score=0.7,
        config_pool=pool, pool_registry=registry,
        apikey_cache=cache, secret_resolver=_FakeResolver(),
        provider_factory=lambda **_kw: provider,  # type: ignore[arg-type]
    )

    assert [h.workspace for h in hits] == ["ws_a", "ws_b"]


@pytest.mark.asyncio
async def test_search_fail_fast_on_workspace_not_found() -> None:
    cache = ApiKeyCache(max_size=8, ttl_seconds=60)
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)  # workspace inexistant
    registry = MagicMock()

    with pytest.raises(WorkspaceNotFound):
        await search(
            refs=[McpWorkspaceRef(name="ghost", api_key="k")],
            query="x", top_k=5, min_score=0.7,
            config_pool=pool, pool_registry=registry,
            apikey_cache=cache, secret_resolver=_FakeResolver(),
        )


@pytest.mark.asyncio
async def test_search_fail_fast_on_bad_apikey(monkeypatch) -> None:
    cache = ApiKeyCache(max_size=8, ttl_seconds=60)
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={
        "id": uuid4(),
        "api_key_hash": "$2b$12$x",
        "indexer_used": "openai/m",
    })
    registry = MagicMock()

    from rag.services import mcp
    monkeypatch.setattr(mcp, "verify_api_key", lambda _k, _h: False)

    with pytest.raises(HTTPException) as exc:
        await search(
            refs=[McpWorkspaceRef(name="ws", api_key="bad")],
            query="x", top_k=5, min_score=0.7,
            config_pool=pool, pool_registry=registry,
            apikey_cache=cache, secret_resolver=_FakeResolver(),
        )
    assert exc.value.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
uv run pytest tests/unit/services/test_mcp_search.py -v
```

Expected: `ImportError: cannot import name 'search' from 'rag.services.mcp'`.

- [ ] **Step 3: Étendre `services/mcp.py` avec `_search_one` et `search`**

Append to `backend/src/rag/services/mcp.py`:

```python
import asyncio
from collections.abc import Callable
from typing import Protocol

import structlog

from rag.db.pool import WorkspacePoolRegistry
from rag.db.workspace_search import vector_search
from rag.indexer.providers.factory import make_provider
from rag.indexer.providers.protocol import EmbeddingProvider
from rag.schemas.mcp import SearchHit

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    def resolve_with_retry(self, ref: str) -> str: ...


def _to_vault_ref(logical_key: str, *, vault_id: str = "rag") -> str:
    return f"${{vault://{vault_id}:{logical_key}}}"


@dataclass(frozen=True)
class _WorkspaceResult:
    workspace_name: str
    indexer_used: str
    hits: list[SearchHit]


async def search(
    *,
    refs: list[McpWorkspaceRef],
    query: str,
    top_k: int,
    min_score: float,
    config_pool: asyncpg.Pool,
    pool_registry: WorkspacePoolRegistry,
    apikey_cache: ApiKeyCache,
    secret_resolver: _ResolverProtocol,
    provider_factory: Callable[..., EmbeddingProvider] | None = None,
) -> list[SearchHit]:
    """Orchestre la recherche MCP multi-workspace.

    Fail-fast : la première exception remontée par un workspace propage
    via `asyncio.gather` et annule les autres tasks. Aucun résultat partiel.

    `provider_factory` par défaut `None` → lookup dynamique de
    `make_provider` au runtime (permet monkey-patching côté tests
    intégration sans avoir à passer le paramètre depuis le router).
    """
    factory = provider_factory if provider_factory is not None else make_provider

    tasks = [
        _search_one(
            ref=r,
            query=query,
            top_k=top_k,
            min_score=min_score,
            config_pool=config_pool,
            pool_registry=pool_registry,
            apikey_cache=apikey_cache,
            secret_resolver=secret_resolver,
            provider_factory=factory,
        )
        for r in refs
    ]
    results = await asyncio.gather(*tasks)
    return [hit for ws_result in results for hit in ws_result.hits]


async def _search_one(
    *,
    ref: McpWorkspaceRef,
    query: str,
    top_k: int,
    min_score: float,
    config_pool: asyncpg.Pool,
    pool_registry: WorkspacePoolRegistry,
    apikey_cache: ApiKeyCache,
    secret_resolver: _ResolverProtocol,
    provider_factory: Callable[..., EmbeddingProvider],
) -> _WorkspaceResult:
    auth = await _authenticate(ref=ref, config_pool=config_pool, apikey_cache=apikey_cache)
    ctx = await _load_workspace_context(config_pool, ref.name)

    api_key: str | None = None
    if ctx["api_key_ref"]:
        api_key = secret_resolver.resolve_with_retry(_to_vault_ref(ctx["api_key_ref"]))

    provider = provider_factory(
        provider=ctx["provider"],
        model=ctx["model"],
        api_key=api_key,
        base_url=ctx["base_url"],
    )
    query_vec = await provider.embed_query(query)

    ws_pool = await pool_registry.get_workspace_pool(ref.name, ctx["rag_cnx"])
    hits = await vector_search(
        ws_pool,
        query_vec=query_vec,
        top_k=top_k,
        min_score=min_score,
        workspace_name=ref.name,
        indexer_used=auth.indexer_used,
    )
    log.info(
        "mcp.search.workspace_done",
        workspace=ref.name,
        hits=len(hits),
        indexer=auth.indexer_used,
    )
    return _WorkspaceResult(
        workspace_name=ref.name,
        indexer_used=auth.indexer_used,
        hits=hits,
    )
```

Note : `dataclass(frozen=True)` est déjà importé via `from dataclasses import dataclass` en T5. Pour `_WorkspaceResult`, la même importation est réutilisée. Vérifier que les imports en haut du fichier incluent tout le nécessaire après cette task.

- [ ] **Step 4: Run tests to verify they pass**

```powershell
uv run pytest tests/unit/services/test_mcp_search.py -v
```

Expected: `5 passed`.

- [ ] **Step 5: Vérifier que tous les tests services/mcp passent (auth + search + normalize)**

```powershell
uv run pytest tests/unit/services/ -v -k mcp
```

Expected: tous verts (normalize 3 + auth 6 + search 5).

- [ ] **Step 6: Lint/format/mypy**

```powershell
uv run ruff check src/rag/services/mcp.py tests/unit/services/test_mcp_search.py
uv run ruff format src/rag/services/mcp.py tests/unit/services/test_mcp_search.py
uv run mypy src/rag/services/mcp.py
```

- [ ] **Step 7: Commit**

```powershell
git add backend/src/rag/services/mcp.py backend/tests/unit/services/test_mcp_search.py
git commit -m "feat(M4c): _search_one + search orchestrator (asyncio.gather)"
```

---

## Task 9: Router `/mcp` + wiring main.py

**Files:**
- Create: `backend/src/rag/api/mcp.py`
- Modify: `backend/src/rag/main.py`

- [ ] **Step 1: Créer le router**

```python
# backend/src/rag/api/mcp.py
from __future__ import annotations

from fastapi import APIRouter, Request

from rag.schemas.mcp import McpRequest, McpResponse
from rag.services.mcp import normalize_refs, search


def build_mcp_router() -> APIRouter:
    """Router de l'endpoint MCP search.

    Pas d'auth FastAPI dependency : la validation api_key est dans le body
    (cf. spec officielle 04-api-mcp.md). `services.mcp._authenticate` valide
    chaque workspace listé.
    """
    router = APIRouter(tags=["mcp"])

    @router.post("/mcp", response_model=McpResponse)
    async def post_mcp(payload: McpRequest, request: Request) -> McpResponse:
        refs = normalize_refs(payload)
        hits = await search(
            refs=refs,
            query=payload.query,
            top_k=payload.top_k,
            min_score=payload.min_score,
            config_pool=request.app.state.pools.config_pool,
            pool_registry=request.app.state.pools,
            apikey_cache=request.app.state.apikey_cache,
            secret_resolver=request.app.state.resolver,
        )
        return McpResponse(query=payload.query, results=hits)

    return router
```

- [ ] **Step 2: Modifier `main.py`**

Edit `backend/src/rag/main.py`:

a) Add import near the other router imports (top of file):
```python
from rag.api.mcp import build_mcp_router
```

b) After the existing `app.include_router(build_workspace_router())` line (inside `build_app`), add:
```python
    app.include_router(build_mcp_router())
```

- [ ] **Step 3: Smoke — l'app boote toujours**

```powershell
cd backend
uv run pytest tests/api/test_main.py tests/api/test_admin_wireup.py -v
```

Expected: pas de régression (les tests existants passent / skip selon DB).

- [ ] **Step 4: Lint/format/mypy**

```powershell
uv run ruff check src/rag/api/mcp.py src/rag/main.py
uv run ruff format src/rag/api/mcp.py src/rag/main.py
uv run mypy src/rag/api/mcp.py src/rag/main.py
```

- [ ] **Step 5: Commit**

```powershell
git add backend/src/rag/api/mcp.py backend/src/rag/main.py
git commit -m "feat(M4c): router /mcp + wiring main.py"
```

---

## Task 10: Tests integration single workspace

**Files:**
- Create: `backend/tests/api/test_mcp_single.py`

- [ ] **Step 1: Écrire les tests integration**

```python
# backend/tests/api/test_mcp_single.py
from __future__ import annotations

import asyncpg
import pytest
from fastapi.testclient import TestClient

from rag.indexer.providers.protocol import EmbeddingProvider
from rag.schemas.mcp import SearchHit


def _make_ws(client: TestClient, admin_headers: dict[str, str], name: str) -> str:
    r = client.post(
        "/workspaces",
        headers=admin_headers,
        json={
            "name": name,
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["api_key"]


class _FakeProvider:
    """Fake provider qui retourne un vecteur déterministe."""

    def __init__(self, vec: list[float]) -> None:
        self._vec = vec
        self.embed_query_calls = 0

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vec for _ in texts]

    async def embed_query(self, _text: str) -> list[float]:
        self.embed_query_calls += 1
        return self._vec


def _inject_fake_provider(client: TestClient, vec: list[float]) -> _FakeProvider:
    """Monkeypatch `make_provider` globally pour ce test."""
    fake = _FakeProvider(vec=vec)
    from rag.services import mcp as mcp_service
    # On override via app.state… non, on patch directement le module ;
    # plus simple : on injecte un attribut conditionnel.
    # Approche réelle : on remplace `make_provider` au niveau module mcp.
    import rag.services.mcp as _mcp_mod
    _mcp_mod.make_provider = lambda **_kw: fake  # type: ignore[assignment]
    # NB : ce test doit restaurer make_provider après — fixture autouse plus bas
    return fake


@pytest.fixture(autouse=True)
def _restore_make_provider() -> None:
    """Restore make_provider après chaque test pour éviter les leaks."""
    import rag.services.mcp as _mcp_mod
    from rag.indexer.providers.factory import make_provider as _real
    yield
    _mcp_mod.make_provider = _real  # type: ignore[assignment]


async def _seed_embedding(
    pg_container: str,
    workspace_name: str,
    path: str,
    chunk_index: int,
    content: str,
    embedding: list[float],
) -> None:
    """Insert manuellement un row embeddings dans rag_ws_<name>."""
    ws_dsn = pg_container.rsplit("/", 1)[0] + f"/rag_ws_{workspace_name}"
    conn = await asyncpg.connect(ws_dsn)
    try:
        from pgvector.asyncpg import register_vector
        await register_vector(conn)
        await conn.execute(
            "INSERT INTO embeddings (path, chunk_index, content, embedding) "
            "VALUES ($1, $2, $3, $4)",
            path, chunk_index, content, embedding,
        )
    finally:
        await conn.close()


def test_mcp_single_returns_top_k_hits(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    import asyncio
    api_key = _make_ws(admin_client, admin_headers, "ws_mcp_a")

    # Crée 3 embeddings avec vecteurs déterministes (dim 1536 pour openai 3-small).
    # On vise des scores cosine ~ 1.0, 0.99, 0.5 en utilisant des vecteurs alignés.
    dim = 1536
    near = [1.0] + [0.0] * (dim - 1)
    mid = [0.99] + [0.01] * (dim - 1)  # vecteur très similaire à near
    far = [0.0] * (dim - 1) + [1.0]

    async def _seed() -> None:
        await _seed_embedding(pg_container, "ws_mcp_a", "near.md", 0, "near content", near)
        await _seed_embedding(pg_container, "ws_mcp_a", "mid.md", 0, "mid content", mid)
        await _seed_embedding(pg_container, "ws_mcp_a", "far.md", 0, "far content", far)
    asyncio.get_event_loop().run_until_complete(_seed())

    _inject_fake_provider(admin_client, vec=near)

    r = admin_client.post(
        "/mcp",
        json={
            "workspace": "ws_mcp_a",
            "api_key": api_key,
            "query": "test query",
            "top_k": 2,
            "min_score": 0.5,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["query"] == "test query"
    paths = [h["path"] for h in body["results"]]
    assert "near.md" in paths
    assert "mid.md" in paths
    # far.md a un cosine proche de 0 → filtré par min_score=0.5
    assert "far.md" not in paths
    assert all(h["workspace"] == "ws_mcp_a" for h in body["results"])
    assert all(h["indexer"] == "openai/text-embedding-3-small" for h in body["results"])


def test_mcp_single_min_score_strict_returns_empty(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    import asyncio
    api_key = _make_ws(admin_client, admin_headers, "ws_mcp_strict")

    dim = 1536
    far = [0.0] * (dim - 1) + [1.0]
    near = [1.0] + [0.0] * (dim - 1)

    async def _seed() -> None:
        await _seed_embedding(pg_container, "ws_mcp_strict", "far.md", 0, "x", far)
    asyncio.get_event_loop().run_until_complete(_seed())

    _inject_fake_provider(admin_client, vec=near)

    r = admin_client.post(
        "/mcp",
        json={
            "workspace": "ws_mcp_strict",
            "api_key": api_key,
            "query": "x",
            "min_score": 0.99,
        },
    )
    assert r.status_code == 200
    assert r.json()["results"] == []


def test_mcp_single_default_top_k_is_5(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    import asyncio
    api_key = _make_ws(admin_client, admin_headers, "ws_mcp_def")

    dim = 1536
    near = [1.0] + [0.0] * (dim - 1)

    async def _seed() -> None:
        for i in range(10):
            await _seed_embedding(
                pg_container, "ws_mcp_def", f"p{i}.md", 0, "x", near,
            )
    asyncio.get_event_loop().run_until_complete(_seed())

    _inject_fake_provider(admin_client, vec=near)

    r = admin_client.post(
        "/mcp",
        json={
            "workspace": "ws_mcp_def",
            "api_key": api_key,
            "query": "x",
            "min_score": 0.0,
        },
    )
    assert r.status_code == 200
    assert len(r.json()["results"]) == 5  # top_k default
```

- [ ] **Step 2: Run tests**

```powershell
cd backend
$env:TEST_POSTGRES_PASSWORD = "i22BfVjVnEG1FhKL0sJ1CuznH73twl1J"
uv run pytest tests/api/test_mcp_single.py -v
```

Expected: `3 passed`. Si problème de cosine score, ajuster les vecteurs `near`/`mid`/`far` pour avoir des cosine prévisibles.

- [ ] **Step 3: Lint/format**

```powershell
uv run ruff check tests/api/test_mcp_single.py
uv run ruff format tests/api/test_mcp_single.py
```

- [ ] **Step 4: Commit**

```powershell
git add backend/tests/api/test_mcp_single.py
git commit -m "test(M4c): integration single workspace (top_k, min_score, dedup)"
```

---

## Task 11: Tests integration multi-workspace

**Files:**
- Create: `backend/tests/api/test_mcp_multi.py`

- [ ] **Step 1: Écrire les tests**

```python
# backend/tests/api/test_mcp_multi.py
from __future__ import annotations

import asyncio

import asyncpg
import pytest
from fastapi.testclient import TestClient

from pgvector.asyncpg import register_vector


def _make_ws(
    client: TestClient,
    admin_headers: dict[str, str],
    name: str,
    *,
    provider: str = "openai",
    model: str = "text-embedding-3-small",
    api_key_ref: str | None = "openai_embedding_key",
    base_url: str | None = None,
) -> str:
    indexer_body: dict[str, object] = {"provider": provider, "model": model}
    if api_key_ref is not None:
        indexer_body["api_key_ref"] = api_key_ref
    if base_url is not None:
        indexer_body["base_url"] = base_url
    r = client.post(
        "/workspaces",
        headers=admin_headers,
        json={"name": name, "indexer": indexer_body},
    )
    assert r.status_code == 201, r.text
    return r.json()["api_key"]


class _FakeProvider:
    def __init__(self, vec: list[float]) -> None:
        self._vec = vec

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vec for _ in texts]

    async def embed_query(self, _text: str) -> list[float]:
        return self._vec


@pytest.fixture(autouse=True)
def _restore_make_provider():  # type: ignore[no-untyped-def]
    import rag.services.mcp as _mod
    from rag.indexer.providers.factory import make_provider as _real
    yield
    _mod.make_provider = _real  # type: ignore[assignment]


async def _seed(pg_container: str, ws: str, path: str, content: str, vec: list[float]) -> None:
    ws_dsn = pg_container.rsplit("/", 1)[0] + f"/rag_ws_{ws}"
    conn = await asyncpg.connect(ws_dsn)
    try:
        await register_vector(conn)
        await conn.execute(
            "INSERT INTO embeddings (path, chunk_index, content, embedding) "
            "VALUES ($1, 0, $2, $3)",
            path, content, vec,
        )
    finally:
        await conn.close()


def test_mcp_multi_returns_hits_from_all_workspaces_in_order(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    key_a = _make_ws(admin_client, admin_headers, "ws_m_a")
    key_b = _make_ws(admin_client, admin_headers, "ws_m_b")

    dim = 1536
    near = [1.0] + [0.0] * (dim - 1)

    async def _go() -> None:
        await _seed(pg_container, "ws_m_a", "a_doc.md", "from a", near)
        await _seed(pg_container, "ws_m_b", "b_doc.md", "from b", near)
    asyncio.get_event_loop().run_until_complete(_go())

    fake = _FakeProvider(vec=near)
    import rag.services.mcp as _mcp_mod
    _mcp_mod.make_provider = lambda **_kw: fake  # type: ignore[assignment]

    r = admin_client.post(
        "/mcp",
        json={
            "workspaces": [
                {"name": "ws_m_a", "api_key": key_a},
                {"name": "ws_m_b", "api_key": key_b},
            ],
            "query": "x",
            "top_k": 5,
            "min_score": 0.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    paths = [h["path"] for h in body["results"]]
    assert paths == ["a_doc.md", "b_doc.md"]


def test_mcp_multi_each_item_carries_correct_workspace_and_indexer(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    key_a = _make_ws(admin_client, admin_headers, "ws_label_a")
    key_b = _make_ws(admin_client, admin_headers, "ws_label_b",
                     provider="voyage", model="voyage-3-lite",
                     api_key_ref="voyage_api_key")

    # voyage-3-lite default dimension = 1024 (depuis model_dimensions M2)
    dim_oa = 1536
    dim_vy = 1024
    vec_oa = [1.0] + [0.0] * (dim_oa - 1)
    vec_vy = [1.0] + [0.0] * (dim_vy - 1)

    async def _go() -> None:
        await _seed(pg_container, "ws_label_a", "a.md", "x", vec_oa)
        await _seed(pg_container, "ws_label_b", "b.md", "x", vec_vy)
    asyncio.get_event_loop().run_until_complete(_go())

    # On a besoin d'un fake provider qui renvoie le bon vecteur selon le model.
    class _DimAwareFake:
        async def embed_texts(self, _t):  # type: ignore[no-untyped-def]
            raise AssertionError("not expected")

        async def embed_query(self, _t):  # type: ignore[no-untyped-def]
            return [1.0] + [0.0] * (self.dim - 1)  # type: ignore[attr-defined]

    def _factory(provider: str, model: str, **_kw):  # type: ignore[no-untyped-def]
        f = _DimAwareFake()
        f.dim = dim_oa if provider == "openai" else dim_vy  # type: ignore[attr-defined]
        return f

    import rag.services.mcp as _mcp_mod
    _mcp_mod.make_provider = _factory  # type: ignore[assignment]

    r = admin_client.post(
        "/mcp",
        json={
            "workspaces": [
                {"name": "ws_label_a", "api_key": key_a},
                {"name": "ws_label_b", "api_key": key_b},
            ],
            "query": "x",
            "min_score": 0.0,
        },
    )
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    by_ws = {h["workspace"]: h for h in results}
    assert by_ws["ws_label_a"]["indexer"] == "openai/text-embedding-3-small"
    assert by_ws["ws_label_b"]["indexer"] == "voyage/voyage-3-lite"


def test_mcp_multi_top_k_applies_per_workspace(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    key_a = _make_ws(admin_client, admin_headers, "ws_topk_a")
    key_b = _make_ws(admin_client, admin_headers, "ws_topk_b")

    dim = 1536
    vec = [1.0] + [0.0] * (dim - 1)

    async def _go() -> None:
        for i in range(5):
            await _seed(pg_container, "ws_topk_a", f"a{i}.md", "x", vec)
            await _seed(pg_container, "ws_topk_b", f"b{i}.md", "x", vec)
    asyncio.get_event_loop().run_until_complete(_go())

    fake = _FakeProvider(vec=vec)
    import rag.services.mcp as _mcp_mod
    _mcp_mod.make_provider = lambda **_kw: fake  # type: ignore[assignment]

    r = admin_client.post(
        "/mcp",
        json={
            "workspaces": [
                {"name": "ws_topk_a", "api_key": key_a},
                {"name": "ws_topk_b", "api_key": key_b},
            ],
            "query": "x",
            "top_k": 2,
            "min_score": 0.0,
        },
    )
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    # 2 par workspace = 4 total
    assert len(results) == 4
    paths_a = [h["path"] for h in results if h["workspace"] == "ws_topk_a"]
    paths_b = [h["path"] for h in results if h["workspace"] == "ws_topk_b"]
    assert len(paths_a) == 2
    assert len(paths_b) == 2
```

- [ ] **Step 2: Run tests**

```powershell
$env:TEST_POSTGRES_PASSWORD = "i22BfVjVnEG1FhKL0sJ1CuznH73twl1J"
uv run pytest tests/api/test_mcp_multi.py -v
```

Expected: `3 passed`.

- [ ] **Step 3: Lint/format**

```powershell
uv run ruff check tests/api/test_mcp_multi.py
uv run ruff format tests/api/test_mcp_multi.py
```

- [ ] **Step 4: Commit**

```powershell
git add backend/tests/api/test_mcp_multi.py
git commit -m "test(M4c): integration multi-workspace (ordre, indexer label, top_k par ws)"
```

---

## Task 12: Tests integration codes erreur

**Files:**
- Create: `backend/tests/api/test_mcp_errors.py`

- [ ] **Step 1: Écrire les tests d'erreurs**

```python
# backend/tests/api/test_mcp_errors.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _make_ws(client: TestClient, admin_headers: dict[str, str], name: str) -> str:
    r = client.post(
        "/workspaces",
        headers=admin_headers,
        json={
            "name": name,
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 201
    return r.json()["api_key"]


class _FakeProvider:
    async def embed_texts(self, texts):  # type: ignore[no-untyped-def]
        return [[0.1] * 1536 for _ in texts]

    async def embed_query(self, _t):  # type: ignore[no-untyped-def]
        return [0.1] * 1536


@pytest.fixture(autouse=True)
def _restore_make_provider():  # type: ignore[no-untyped-def]
    import rag.services.mcp as _mod
    from rag.indexer.providers.factory import make_provider as _real
    yield
    _mod.make_provider = _real  # type: ignore[assignment]


def _inject_fake_provider() -> None:
    import rag.services.mcp as _mcp_mod
    _mcp_mod.make_provider = lambda **_kw: _FakeProvider()  # type: ignore[assignment]


def test_mcp_422_for_empty_body(
    admin_client: TestClient, cleanup_ws_dbs_api: None
) -> None:
    r = admin_client.post("/mcp", json={})
    assert r.status_code == 422


def test_mcp_422_for_missing_query(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_err_q")
    r = admin_client.post(
        "/mcp",
        json={"workspace": "ws_err_q", "api_key": "x"},
    )
    assert r.status_code == 422


def test_mcp_422_for_mix_workspace_and_workspaces(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    r = admin_client.post(
        "/mcp",
        json={
            "workspace": "ws_a",
            "api_key": "k",
            "workspaces": [{"name": "ws_b", "api_key": "k2"}],
            "query": "x",
        },
    )
    assert r.status_code == 422


def test_mcp_422_for_top_k_above_50(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_err_topk")
    _inject_fake_provider()
    r = admin_client.post(
        "/mcp",
        json={
            "workspace": "ws_err_topk", "api_key": api_key,
            "query": "x", "top_k": 51,
        },
    )
    assert r.status_code == 422


def test_mcp_422_for_min_score_above_one(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_err_minscore")
    _inject_fake_provider()
    r = admin_client.post(
        "/mcp",
        json={
            "workspace": "ws_err_minscore", "api_key": api_key,
            "query": "x", "min_score": 1.5,
        },
    )
    assert r.status_code == 422


def test_mcp_404_for_unknown_workspace(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _inject_fake_provider()
    r = admin_client.post(
        "/mcp",
        json={"workspace": "ghost", "api_key": "x", "query": "y"},
    )
    assert r.status_code == 404
    assert r.json()["error"] == "workspace_not_found"


def test_mcp_401_for_bad_api_key(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_err_badkey")
    _inject_fake_provider()
    r = admin_client.post(
        "/mcp",
        json={
            "workspace": "ws_err_badkey",
            "api_key": "not-the-real-one",
            "query": "y",
        },
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


def test_mcp_multi_fail_fast_one_bad_apikey(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key_a = _make_ws(admin_client, admin_headers, "ws_ff_a")
    _make_ws(admin_client, admin_headers, "ws_ff_b")
    _inject_fake_provider()
    r = admin_client.post(
        "/mcp",
        json={
            "workspaces": [
                {"name": "ws_ff_a", "api_key": key_a},
                {"name": "ws_ff_b", "api_key": "wrong-key"},
            ],
            "query": "x",
        },
    )
    # Une des tasks lève 401 → propage. Ordre asyncio non déterministe :
    # si ws_ff_b finit en premier, on a 401 ; si ws_ff_a finit en premier,
    # la tâche ws_ff_b est annulée — l'exception 401 propage quand même.
    assert r.status_code == 401
```

- [ ] **Step 2: Run tests**

```powershell
$env:TEST_POSTGRES_PASSWORD = "i22BfVjVnEG1FhKL0sJ1CuznH73twl1J"
uv run pytest tests/api/test_mcp_errors.py -v
```

Expected: `8 passed`.

- [ ] **Step 3: Lint/format**

```powershell
uv run ruff check tests/api/test_mcp_errors.py
uv run ruff format tests/api/test_mcp_errors.py
```

- [ ] **Step 4: Commit**

```powershell
git add backend/tests/api/test_mcp_errors.py
git commit -m "test(M4c): integration codes erreurs (422/404/401 + fail-fast)"
```

---

## Task 13: Smoke E2E Ollama (opt-in)

**Files:**
- Create: `backend/tests/api/test_mcp_e2e_ollama_smoke.py`

- [ ] **Step 1: Écrire le smoke**

```python
# backend/tests/api/test_mcp_e2e_ollama_smoke.py
from __future__ import annotations

import asyncio
import os

import asyncpg
import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.smoke


@pytest.fixture
def ollama_url() -> str:
    url = os.environ.get("OLLAMA_TEST_URL")
    if not url:
        pytest.skip("OLLAMA_TEST_URL non défini — smoke /mcp Ollama sauté.")
    return url


def test_mcp_e2e_ollama_search_returns_relevant_doc(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
    ollama_url: str,
) -> None:
    """Crée workspace Ollama, push 2 docs sémantiquement distincts,
    /mcp avec une query proche du doc A doit retourner doc A en tête."""
    r = admin_client.post(
        "/workspaces",
        headers=admin_headers,
        json={
            "name": "ws_mcp_smoke",
            "indexer": {
                "provider": "ollama",
                "model": "nomic-embed-text",
                "base_url": ollama_url,
            },
        },
    )
    assert r.status_code == 201
    api_key = r.json()["api_key"]
    push_headers = {"Authorization": f"Bearer {api_key}"}

    # Push 2 documents sur des sujets distincts.
    r1 = admin_client.post(
        "/workspaces/ws_mcp_smoke/index",
        headers=push_headers,
        json={
            "path": "topic/docker.md",
            "content": "Docker provides containerization through Linux namespaces and cgroups.",
        },
    )
    assert r1.status_code == 200, r1.text

    r2 = admin_client.post(
        "/workspaces/ws_mcp_smoke/index",
        headers=push_headers,
        json={
            "path": "topic/cooking.md",
            "content": "To make a perfect omelette, beat the eggs with cream and salt.",
        },
    )
    assert r2.status_code == 200, r2.text

    # Recherche : query proche du sujet Docker
    r3 = admin_client.post(
        "/mcp",
        json={
            "workspace": "ws_mcp_smoke",
            "api_key": api_key,
            "query": "How do Linux containers work?",
            "top_k": 5,
            "min_score": 0.0,
        },
    )
    assert r3.status_code == 200, r3.text
    body = r3.json()
    assert len(body["results"]) >= 1
    # Le doc docker doit être en tête (score plus élevé)
    top_path = body["results"][0]["path"]
    assert top_path == "topic/docker.md", f"expected docker.md on top, got {top_path}"
    assert body["results"][0]["score"] > 0.3  # cosine raisonnable pour Ollama
```

- [ ] **Step 2: Vérifier que le smoke est skippé par défaut**

```powershell
uv run pytest tests/api/test_mcp_e2e_ollama_smoke.py -v
```

Expected: `1 deselected`.

- [ ] **Step 3: Smoke avec Ollama (si dispo)**

```powershell
$env:OLLAMA_TEST_URL = "http://192.168.10.80:11434"
$env:TEST_POSTGRES_PASSWORD = "i22BfVjVnEG1FhKL0sJ1CuznH73twl1J"
uv run pytest tests/api/test_mcp_e2e_ollama_smoke.py -m smoke -v
```

Expected si Ollama dispo : `1 passed`. Sinon `1 skipped` (env var manque) ou erreur de réseau (acceptable, à reporter).

- [ ] **Step 4: Lint/format**

```powershell
uv run ruff check tests/api/test_mcp_e2e_ollama_smoke.py
uv run ruff format tests/api/test_mcp_e2e_ollama_smoke.py
```

- [ ] **Step 5: Commit**

```powershell
git add backend/tests/api/test_mcp_e2e_ollama_smoke.py
git commit -m "test(M4c): smoke E2E Ollama (push 2 docs + /mcp top-1)"
```

---

## Task 14: Quality gate

**Files:**
- No code changes (sauf corrections si gates échouent)

- [ ] **Step 1: ruff check + format**

```powershell
cd backend
uv run ruff check src tests
uv run ruff format --check src tests
```

Expected: clean.

- [ ] **Step 2: mypy strict**

```powershell
uv run mypy src/rag
```

Expected: `Success: no issues found in N source files`.

- [ ] **Step 3: pytest complet avec couverture**

```powershell
$env:TEST_POSTGRES_PASSWORD = "i22BfVjVnEG1FhKL0sJ1CuznH73twl1J"
uv run pytest --cov=src/rag --cov-report=term-missing -q
```

Expected:
- Tous les tests verts (non-smoke).
- Couverture globale ≥ 95%.
- Modules M4c ≥ 95% chacun :
  - `services/mcp.py`
  - `api/mcp.py`
  - `db/workspace_search.py`
  - `schemas/mcp.py`
  - `indexer/providers/{openai,voyage,ollama}.py` (sur les nouvelles méthodes `embed_query`)

- [ ] **Step 4: Si coverage insuffisant sur un module M4c — fix**

Identifier les branches non couvertes via `--cov-report=term-missing`. Ajouter des tests unitaires ciblés.

- [ ] **Step 5: Commit si corrections appliquées**

```powershell
git add -u
git commit -m "chore(M4c): corrections quality gate (lint/coverage)"
```

---

## Task 15: Deploy LXC 303 + tag m4c-done

**Files:**
- No code changes

- [ ] **Step 1: Push la branche**

```powershell
git push origin dev
```

- [ ] **Step 2: Déployer sur LXC 303**

```powershell
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && ./dev-deploy.sh'"
```

Attendre la fin (build + restart + healthcheck OK).

- [ ] **Step 3: Smoke API**

```powershell
curl http://192.168.10.184:8000/health
curl http://192.168.10.184:8000/version
```

Expected : `/health` `{"status":"ok"}` ; `/version` git = HEAD du dev.

- [ ] **Step 4: Smoke /mcp end-to-end (optionnel — requires Ollama)**

Si l'Ollama LXC 80 est joignable depuis 303 :
- Créer un workspace Ollama via master key
- Push 1 doc
- Lancer `POST /mcp` avec query proche
- Vérifier 200 + `results` non vide

Cette étape est optionnelle car déjà couverte par le smoke local (T13). Skip si pas d'accès facile au master key sur 303.

- [ ] **Step 5: Tag m4c-done**

```powershell
git tag -a m4c-done -m "M4c: API MCP search POST /mcp (single + multi-workspace)"
git push origin m4c-done
```

Expected: `* [new tag] m4c-done -> m4c-done`.

---

## Récapitulatif de couverture (cible)

| Module | Cible |
|---|---|
| `backend/src/rag/services/mcp.py` | ≥ 95% |
| `backend/src/rag/api/mcp.py` | 100% (couvert via integration) |
| `backend/src/rag/db/workspace_search.py` | 100% |
| `backend/src/rag/schemas/mcp.py` | 100% |
| `backend/src/rag/indexer/providers/openai.py` (embed_query) | 100% sur la nouvelle méthode |
| `backend/src/rag/indexer/providers/voyage.py` (embed_query) | 100% sur la nouvelle méthode |
| `backend/src/rag/indexer/providers/ollama.py` (embed_query) | 100% sur la nouvelle méthode |
| **Couverture globale projet** | ≥ 95% (maintenir le niveau M4b) |

## Hors scope (rappel)

- Cache du résultat `embed_query` inter-requête.
- Rate-limiting applicatif côté `/mcp`.
- Granularité scopes api_key (read-only vs write-only).
- Reranker post-cosine.
- Hybrid search (BM25 + vector).
- Stream SSE.
- `errors[]` field en réponse (fail-fast assumé).
- Groupage explicite par indexer dans la réponse (chaque hit porte son indexer).
- Tuning `ivfflat.probes` (utilisation des défauts pgvector).
- Configuration redact api_key dans Caddyfile logs (à documenter dans la PR mais hors code M4c).
