# M8 — Reranking backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer le reranking par workspace : table `rerank_configs`, 3 providers (Cohere/Voyage/Ollama), endpoints admin CRUD, intégration dans le flow MCP search (per-workspace avant merge), fail-fast sur défaillance provider, backward-compat (opt-in).

**Architecture:** Réplique le pattern des embeddings (M4a) : Protocol + factory + 3 implémentations httpx. Le rerank s'insère dans `_search_one()` après `vector_search` (qui retourne `top_k_pre_rerank` candidats), trie via le provider, garde le top_k final. Workspaces sans `rerank_configs` row = comportement inchangé.

**Tech Stack:** Python 3.12, asyncpg, httpx.AsyncClient, Pydantic v2, pytest + pytest-asyncio. Pattern de référence : `backend/src/rag/indexer/providers/` (M4a).

**Spec design** : `docs/superpowers/specs/2026-05-17-M8-backend-reranking-design.md`

---

## File Structure

| Fichier | Statut | Responsabilité |
|---|---|---|
| `backend/migrations/011_rerank_configs.sql` | **Create** | Table rerank_configs + FK CASCADE + CHECK |
| `backend/src/rag/schemas/admin.py` | **Modify** | +RerankSpec, +RerankConfigResponse |
| `backend/src/rag/rerank/__init__.py` | **Create** | empty package marker |
| `backend/src/rag/rerank/protocol.py` | **Create** | RerankProvider Protocol + 4 exceptions |
| `backend/src/rag/rerank/providers/__init__.py` | **Create** | empty package marker |
| `backend/src/rag/rerank/providers/cohere.py` | **Create** | CohereRerankProvider (httpx) |
| `backend/src/rag/rerank/providers/voyage.py` | **Create** | VoyageRerankProvider (httpx) |
| `backend/src/rag/rerank/providers/ollama.py` | **Create** | OllamaRerankProvider (httpx) |
| `backend/src/rag/rerank/providers/factory.py` | **Create** | make_rerank_provider |
| `backend/src/rag/services/rerank_configs.py` | **Create** | get / upsert (eager validation) / delete |
| `backend/src/rag/api/admin.py` | **Modify** | +3 endpoints GET/PUT/DELETE /rerank |
| `backend/src/rag/services/mcp.py` | **Modify** | LEFT JOIN rerank, intégration `_search_one`, rerank_factory injectable |
| `backend/tests/integration/test_migration_011_rerank_configs.py` | **Create** | Schéma + FK CASCADE + CHECK |
| `backend/tests/unit/rerank/test_cohere.py` | **Create** | 5 cas (parse + 4 erreurs) |
| `backend/tests/unit/rerank/test_voyage.py` | **Create** | idem |
| `backend/tests/unit/rerank/test_ollama.py` | **Create** | idem |
| `backend/tests/unit/rerank/test_factory.py` | **Create** | 3 providers + unknown + missing api_key/base_url |
| `backend/tests/integration/test_services_rerank_configs.py` | **Create** | get/upsert/delete + eager validation |
| `backend/tests/api/test_admin_workspaces_rerank.py` | **Create** | GET 200/404, PUT upsert, DELETE 204 |
| `backend/tests/integration/test_mcp_with_rerank.py` | **Create** | E2E avec et sans rerank, singleton skip |
| `backend/tests/integration/test_mcp_rerank_fail_fast.py` | **Create** | Provider lève → propagation |
| `backend/.env.example` | **Modify** | Doc COHERE_RERANK_* / VOYAGE_RERANK_* |
| `specs/09-roadmap.md` | **Modify** | Marquer M8 livré |

---

## Task 1: Migration 011 + schemas Pydantic

**Files:**
- Create: `backend/migrations/011_rerank_configs.sql`
- Modify: `backend/src/rag/schemas/admin.py`
- Create: `backend/tests/integration/test_migration_011_rerank_configs.py`

- [ ] **Step 1: Écrire le test de schéma (rouge)**

`backend/tests/integration/test_migration_011_rerank_configs.py` :

```python
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_rerank_configs_columns(session_pool: asyncpg.Pool) -> None:
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS rerank_configs, indexer_configs, "
            "workspace_sources, index_jobs, indexed_documents, "
            "workspaces, schema_migrations CASCADE"
        )
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]: r["data_type"]
            for r in await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'rerank_configs'"
            )
        }
    expected = {
        "workspace_id", "provider", "model", "base_url", "api_key_ref",
        "top_k_pre_rerank", "created_at", "updated_at",
    }
    assert expected.issubset(cols.keys())
    assert cols["workspace_id"] == "uuid"
    assert cols["top_k_pre_rerank"] == "integer"


@pytest.mark.asyncio
async def test_rerank_configs_fk_cascade(session_pool: asyncpg.Pool) -> None:
    """Supprimer un workspace supprime sa rerank_config (ON DELETE CASCADE)."""
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS rerank_configs, indexer_configs, "
            "workspace_sources, index_jobs, indexed_documents, "
            "workspaces, schema_migrations CASCADE"
        )
    await run_migrations(session_pool, MIGRATIONS_DIR)

    dek = "x" * 32
    from hashlib import sha256
    api_key = "smoke"
    fp = sha256(api_key.encode()).hexdigest()
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ($1, pgp_sym_encrypt($2::text, $3::text)::bytea, $4, 'c', 'b') RETURNING id",
            "ws_cascade", api_key, dek, fp,
        )
        await conn.execute(
            "INSERT INTO rerank_configs (workspace_id, provider, model) "
            "VALUES ($1, 'cohere', 'rerank-v3.5')",
            ws_id,
        )
        await conn.execute("DELETE FROM workspaces WHERE id = $1", ws_id)
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM rerank_configs WHERE workspace_id = $1", ws_id,
        )
    assert count == 0


@pytest.mark.asyncio
async def test_rerank_configs_check_top_k_positive(session_pool: asyncpg.Pool) -> None:
    """CHECK contrainte top_k_pre_rerank > 0."""
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS rerank_configs, indexer_configs, "
            "workspace_sources, index_jobs, indexed_documents, "
            "workspaces, schema_migrations CASCADE"
        )
    await run_migrations(session_pool, MIGRATIONS_DIR)

    dek = "x" * 32
    from hashlib import sha256
    api_key = "smoke2"
    fp = sha256(api_key.encode()).hexdigest()
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ($1, pgp_sym_encrypt($2::text, $3::text)::bytea, $4, 'c', 'b') RETURNING id",
            "ws_check", api_key, dek, fp,
        )
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO rerank_configs (workspace_id, provider, model, top_k_pre_rerank) "
                "VALUES ($1, 'cohere', 'rerank-v3.5', 0)",
                ws_id,
            )
```

- [ ] **Step 2: Run rouge**

Sur LXC test (cf. mémoire `test-execution-pattern`). Si CTID 401 absent, créer via `./scripts/run-test.sh` (CLEANUP=0).

```bash
cd backend
uv run pytest tests/integration/test_migration_011_rerank_configs.py -v
```
Expected : 3 FAIL (table `rerank_configs` n'existe pas).

- [ ] **Step 3: Écrire la migration**

`backend/migrations/011_rerank_configs.sql` :

```sql
-- Migration 011 — rerank_configs : config rerank par workspace (opt-in)
--
-- Workspace SANS row dans cette table → pas de rerank (comportement par défaut).
-- Cascade ON DELETE : suppression workspace → suppression rerank_config auto.

CREATE TABLE rerank_configs (
    workspace_id        UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    provider            TEXT NOT NULL,
    model               TEXT NOT NULL,
    base_url            TEXT,
    api_key_ref         TEXT,
    top_k_pre_rerank    INT NOT NULL DEFAULT 50 CHECK (top_k_pre_rerank > 0),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- [ ] **Step 4: Run vert**

```bash
uv run pytest tests/integration/test_migration_011_rerank_configs.py -v
```
Expected : 3 PASS.

- [ ] **Step 5: Ajouter les schemas Pydantic**

Dans `backend/src/rag/schemas/admin.py`, ajouter (idéalement après `ModelEntry`) :

```python
from typing import Literal

class RerankSpec(BaseModel):
    """Body PUT /workspaces/{name}/rerank."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    provider: Literal["cohere", "voyage", "ollama"]
    model: str = Field(min_length=1)
    api_key_ref: str | None = None
    base_url: str | None = None
    top_k_pre_rerank: int = Field(default=50, gt=0, le=500)


class RerankConfigResponse(BaseModel):
    """Réponse GET / PUT /workspaces/{name}/rerank."""

    workspace_id: UUID
    provider: str
    model: str
    api_key_ref: str | None
    base_url: str | None
    top_k_pre_rerank: int
    created_at: str
    updated_at: str
```

Vérifier que `UUID` (`from uuid import UUID`) et `Literal` sont importés en tête de fichier (à ajouter si manquants).

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/011_rerank_configs.sql \
        backend/src/rag/schemas/admin.py \
        backend/tests/integration/test_migration_011_rerank_configs.py
git commit -m "feat(M8-T1): migration 011 rerank_configs + schemas RerankSpec/Response"
```

---

## Task 2: Protocol RerankProvider + exceptions

**Files:**
- Create: `backend/src/rag/rerank/__init__.py`
- Create: `backend/src/rag/rerank/protocol.py`

- [ ] **Step 1: Créer le package**

```bash
mkdir -p backend/src/rag/rerank/providers
touch backend/src/rag/rerank/__init__.py
touch backend/src/rag/rerank/providers/__init__.py
```

- [ ] **Step 2: Écrire `protocol.py`**

`backend/src/rag/rerank/protocol.py` :

```python
from __future__ import annotations

from typing import Protocol


class RerankProviderError(RuntimeError):
    """Base des erreurs reranker. Sous-classes : Auth / RateLimited / Unreachable."""


class RerankAuthError(RerankProviderError):
    """HTTP 401/403 — api_key invalide ou révoquée."""


class RerankRateLimited(RerankProviderError):  # noqa: N818
    """HTTP 429 — quota atteint."""


class RerankProviderUnreachable(RerankProviderError):  # noqa: N818
    """Timeout / connection refused / HTTP 5xx."""


class RerankProvider(Protocol):
    """Reranke des documents selon une query, retourne les indices triés
    par pertinence décroissante.

    Convention : `len(retour) ≤ min(top_k, len(documents))`. Les indices
    sont dans `range(len(documents))`. L'ordre est strict : indice à
    position 0 = document le plus pertinent.
    """

    async def rerank(
        self, *, query: str, documents: list[str], top_k: int,
    ) -> list[int]:
        ...
```

- [ ] **Step 3: Smoke**

```bash
cd backend
uv run python -c "from rag.rerank.protocol import RerankProvider, RerankAuthError, RerankRateLimited, RerankProviderUnreachable; print('ok')"
```
Expected : `ok` (imports résolvent).

- [ ] **Step 4: Commit**

```bash
git add backend/src/rag/rerank/__init__.py \
        backend/src/rag/rerank/providers/__init__.py \
        backend/src/rag/rerank/protocol.py
git commit -m "feat(M8-T2): protocol RerankProvider + hiérarchie exceptions"
```

---

## Task 3: Provider Cohere + tests unit

**Files:**
- Create: `backend/src/rag/rerank/providers/cohere.py`
- Create: `backend/tests/unit/rerank/test_cohere.py`

- [ ] **Step 1: Créer le dossier de tests**

```bash
mkdir -p backend/tests/unit/rerank
touch backend/tests/unit/rerank/__init__.py
```

- [ ] **Step 2: Écrire les 5 tests (rouge)**

`backend/tests/unit/rerank/test_cohere.py` :

```python
from __future__ import annotations

import httpx
import pytest

from rag.rerank.protocol import (
    RerankAuthError,
    RerankProviderUnreachable,
    RerankRateLimited,
)
from rag.rerank.providers.cohere import CohereRerankProvider


def _mock_transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_cohere_returns_sorted_indices() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.cohere.com"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json={
            "results": [
                {"index": 2, "relevance_score": 0.99},
                {"index": 0, "relevance_score": 0.50},
                {"index": 1, "relevance_score": 0.10},
            ],
        })
    provider = CohereRerankProvider(
        model="rerank-v3.5", api_key="test-key",
        transport=_mock_transport(handler),
    )
    indices = await provider.rerank(query="q", documents=["a", "b", "c"], top_k=3)
    assert indices == [2, 0, 1]


@pytest.mark.asyncio
async def test_cohere_auth_error_on_401() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "invalid key"})
    provider = CohereRerankProvider(
        model="rerank-v3.5", api_key="bad",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankAuthError):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_cohere_rate_limited_on_429() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(429)
    provider = CohereRerankProvider(
        model="rerank-v3.5", api_key="k",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankRateLimited):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_cohere_unreachable_on_5xx() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(503)
    provider = CohereRerankProvider(
        model="rerank-v3.5", api_key="k",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_cohere_unreachable_on_timeout() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout")
    provider = CohereRerankProvider(
        model="rerank-v3.5", api_key="k",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)
```

- [ ] **Step 3: Run rouge**

```bash
cd backend
uv run pytest tests/unit/rerank/test_cohere.py -v
```
Expected : 5 FAIL (CohereRerankProvider n'existe pas).

- [ ] **Step 4: Implémenter `CohereRerankProvider`**

`backend/src/rag/rerank/providers/cohere.py` :

```python
from __future__ import annotations

from typing import Any

import httpx
import structlog

from rag.rerank.protocol import (
    RerankAuthError,
    RerankProviderUnreachable,
    RerankRateLimited,
)

log = structlog.get_logger(__name__)

_URL = "https://api.cohere.com/v2/rerank"
_TIMEOUT = 30.0


class CohereRerankProvider:
    """Reranker Cohere v2. Pattern aligné sur les providers d'embedding (M4a)."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._transport = transport

    async def rerank(
        self, *, query: str, documents: list[str], top_k: int,
    ) -> list[int]:
        if not documents:
            return []
        body: dict[str, Any] = {
            "model": self._model,
            "query": query,
            "documents": documents,
            "top_n": min(top_k, len(documents)),
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=_TIMEOUT,
            ) as client:
                resp = await client.post(_URL, json=body, headers=headers)
        except httpx.TimeoutException as e:
            raise RerankProviderUnreachable(f"cohere timeout: {e}") from e
        except httpx.RequestError as e:
            raise RerankProviderUnreachable(f"cohere network: {e}") from e

        if resp.status_code in (401, 403):
            raise RerankAuthError(f"cohere auth: HTTP {resp.status_code}")
        if resp.status_code == 429:
            raise RerankRateLimited("cohere rate limited (429)")
        if 500 <= resp.status_code < 600:
            raise RerankProviderUnreachable(f"cohere 5xx: HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise RerankProviderUnreachable(
                f"cohere unexpected {resp.status_code}: {resp.text}"
            )

        data = resp.json()
        results = data.get("results", [])
        return [int(r["index"]) for r in results]
```

- [ ] **Step 5: Run vert**

```bash
uv run pytest tests/unit/rerank/test_cohere.py -v
```
Expected : 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/rag/rerank/providers/cohere.py \
        backend/tests/unit/rerank/__init__.py \
        backend/tests/unit/rerank/test_cohere.py
git commit -m "feat(M8-T3): CohereRerankProvider + 5 tests unit (parse + 4 erreurs)"
```

---

## Task 4: Provider Voyage + tests unit

**Files:**
- Create: `backend/src/rag/rerank/providers/voyage.py`
- Create: `backend/tests/unit/rerank/test_voyage.py`

- [ ] **Step 1: Écrire les 5 tests (rouge)**

`backend/tests/unit/rerank/test_voyage.py` (clone du test_cohere avec URL Voyage et format réponse Voyage) :

```python
from __future__ import annotations

import httpx
import pytest

from rag.rerank.protocol import (
    RerankAuthError,
    RerankProviderUnreachable,
    RerankRateLimited,
)
from rag.rerank.providers.voyage import VoyageRerankProvider


def _mock_transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_voyage_returns_sorted_indices() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.voyageai.com"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json={
            "data": [
                {"index": 1, "relevance_score": 0.95},
                {"index": 2, "relevance_score": 0.80},
                {"index": 0, "relevance_score": 0.40},
            ],
        })
    provider = VoyageRerankProvider(
        model="rerank-2", api_key="test-key",
        transport=_mock_transport(handler),
    )
    indices = await provider.rerank(query="q", documents=["a", "b", "c"], top_k=3)
    assert indices == [1, 2, 0]


@pytest.mark.asyncio
async def test_voyage_auth_error_on_401() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(401)
    provider = VoyageRerankProvider(
        model="rerank-2", api_key="bad",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankAuthError):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_voyage_rate_limited_on_429() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(429)
    provider = VoyageRerankProvider(
        model="rerank-2", api_key="k",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankRateLimited):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_voyage_unreachable_on_5xx() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(502)
    provider = VoyageRerankProvider(
        model="rerank-2", api_key="k",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_voyage_unreachable_on_timeout() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")
    provider = VoyageRerankProvider(
        model="rerank-2", api_key="k",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)
```

- [ ] **Step 2: Run rouge**

```bash
uv run pytest tests/unit/rerank/test_voyage.py -v
```
Expected : 5 FAIL.

- [ ] **Step 3: Implémenter `VoyageRerankProvider`**

`backend/src/rag/rerank/providers/voyage.py` :

```python
from __future__ import annotations

from typing import Any

import httpx
import structlog

from rag.rerank.protocol import (
    RerankAuthError,
    RerankProviderUnreachable,
    RerankRateLimited,
)

log = structlog.get_logger(__name__)

_URL = "https://api.voyageai.com/v1/rerank"
_TIMEOUT = 30.0


class VoyageRerankProvider:
    """Reranker Voyage AI v1."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._transport = transport

    async def rerank(
        self, *, query: str, documents: list[str], top_k: int,
    ) -> list[int]:
        if not documents:
            return []
        body: dict[str, Any] = {
            "query": query,
            "documents": documents,
            "model": self._model,
            "top_k": min(top_k, len(documents)),
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=_TIMEOUT,
            ) as client:
                resp = await client.post(_URL, json=body, headers=headers)
        except httpx.TimeoutException as e:
            raise RerankProviderUnreachable(f"voyage timeout: {e}") from e
        except httpx.RequestError as e:
            raise RerankProviderUnreachable(f"voyage network: {e}") from e

        if resp.status_code in (401, 403):
            raise RerankAuthError(f"voyage auth: HTTP {resp.status_code}")
        if resp.status_code == 429:
            raise RerankRateLimited("voyage rate limited (429)")
        if 500 <= resp.status_code < 600:
            raise RerankProviderUnreachable(f"voyage 5xx: HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise RerankProviderUnreachable(
                f"voyage unexpected {resp.status_code}: {resp.text}"
            )

        data = resp.json()
        items = data.get("data", [])
        return [int(r["index"]) for r in items]
```

- [ ] **Step 4: Run vert**

```bash
uv run pytest tests/unit/rerank/test_voyage.py -v
```
Expected : 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/rag/rerank/providers/voyage.py \
        backend/tests/unit/rerank/test_voyage.py
git commit -m "feat(M8-T4): VoyageRerankProvider + 5 tests unit"
```

---

## Task 5: Provider Ollama + tests unit

**Files:**
- Create: `backend/src/rag/rerank/providers/ollama.py`
- Create: `backend/tests/unit/rerank/test_ollama.py`

- [ ] **Step 1: Écrire les 5 tests (rouge)**

`backend/tests/unit/rerank/test_ollama.py` :

```python
from __future__ import annotations

import httpx
import pytest

from rag.rerank.protocol import (
    RerankAuthError,
    RerankProviderUnreachable,
    RerankRateLimited,
)
from rag.rerank.providers.ollama import OllamaRerankProvider


def _mock_transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_ollama_returns_sorted_indices() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/api/rerank" in str(request.url)
        return httpx.Response(200, json={
            "results": [
                {"index": 0, "relevance_score": 0.7},
                {"index": 2, "relevance_score": 0.5},
            ],
        })
    provider = OllamaRerankProvider(
        model="bge-reranker-v2-m3",
        base_url="http://localhost:11434",
        transport=_mock_transport(handler),
    )
    indices = await provider.rerank(query="q", documents=["a", "b", "c"], top_k=2)
    assert indices == [0, 2]


@pytest.mark.asyncio
async def test_ollama_auth_error_on_401() -> None:
    """Ollama n'a pas d'auth normalement, mais on traite 401/403 par symétrie."""
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(401)
    provider = OllamaRerankProvider(
        model="bge", base_url="http://localhost:11434",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankAuthError):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_ollama_rate_limited_on_429() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(429)
    provider = OllamaRerankProvider(
        model="bge", base_url="http://localhost:11434",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankRateLimited):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_ollama_unreachable_on_5xx() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(500)
    provider = OllamaRerankProvider(
        model="bge", base_url="http://localhost:11434",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_ollama_unreachable_on_timeout() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")
    provider = OllamaRerankProvider(
        model="bge", base_url="http://localhost:11434",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)
```

- [ ] **Step 2: Run rouge**

```bash
uv run pytest tests/unit/rerank/test_ollama.py -v
```
Expected : 5 FAIL.

- [ ] **Step 3: Implémenter `OllamaRerankProvider`**

`backend/src/rag/rerank/providers/ollama.py` :

```python
from __future__ import annotations

from typing import Any

import httpx
import structlog

from rag.rerank.protocol import (
    RerankAuthError,
    RerankProviderUnreachable,
    RerankRateLimited,
)

log = structlog.get_logger(__name__)

_TIMEOUT = 30.0


class OllamaRerankProvider:
    """Reranker Ollama local (depuis Ollama 0.4+).

    Format de réponse de référence (à adapter si l'API Ollama évolue) :
        {"results": [{"index": int, "relevance_score": float}, ...]}
    """

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    async def rerank(
        self, *, query: str, documents: list[str], top_k: int,
    ) -> list[int]:
        if not documents:
            return []
        url = f"{self._base_url}/api/rerank"
        body: dict[str, Any] = {
            "model": self._model,
            "query": query,
            "documents": documents,
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=_TIMEOUT,
            ) as client:
                resp = await client.post(url, json=body)
        except httpx.TimeoutException as e:
            raise RerankProviderUnreachable(f"ollama timeout: {e}") from e
        except httpx.RequestError as e:
            raise RerankProviderUnreachable(f"ollama network: {e}") from e

        if resp.status_code in (401, 403):
            raise RerankAuthError(f"ollama auth: HTTP {resp.status_code}")
        if resp.status_code == 429:
            raise RerankRateLimited("ollama rate limited (429)")
        if 500 <= resp.status_code < 600:
            raise RerankProviderUnreachable(f"ollama 5xx: HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise RerankProviderUnreachable(
                f"ollama unexpected {resp.status_code}: {resp.text}"
            )

        data = resp.json()
        results = data.get("results", [])
        indices = [int(r["index"]) for r in results]
        return indices[:top_k]
```

- [ ] **Step 4: Run vert**

```bash
uv run pytest tests/unit/rerank/test_ollama.py -v
```
Expected : 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/rag/rerank/providers/ollama.py \
        backend/tests/unit/rerank/test_ollama.py
git commit -m "feat(M8-T5): OllamaRerankProvider + 5 tests unit"
```

---

## Task 6: Factory + tests

**Files:**
- Create: `backend/src/rag/rerank/providers/factory.py`
- Create: `backend/tests/unit/rerank/test_factory.py`

- [ ] **Step 1: Écrire les tests (rouge)**

`backend/tests/unit/rerank/test_factory.py` :

```python
from __future__ import annotations

import pytest

from rag.rerank.providers.cohere import CohereRerankProvider
from rag.rerank.providers.factory import make_rerank_provider
from rag.rerank.providers.ollama import OllamaRerankProvider
from rag.rerank.providers.voyage import VoyageRerankProvider


def test_factory_cohere() -> None:
    p = make_rerank_provider(
        provider="cohere", model="rerank-v3.5", api_key="k", base_url=None,
    )
    assert isinstance(p, CohereRerankProvider)


def test_factory_voyage() -> None:
    p = make_rerank_provider(
        provider="voyage", model="rerank-2", api_key="k", base_url=None,
    )
    assert isinstance(p, VoyageRerankProvider)


def test_factory_ollama() -> None:
    p = make_rerank_provider(
        provider="ollama", model="bge", api_key=None,
        base_url="http://localhost:11434",
    )
    assert isinstance(p, OllamaRerankProvider)


def test_factory_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown rerank provider"):
        make_rerank_provider(
            provider="nope", model="m", api_key="k", base_url=None,
        )


def test_factory_cohere_missing_api_key() -> None:
    with pytest.raises(ValueError, match="cohere requires api_key"):
        make_rerank_provider(
            provider="cohere", model="m", api_key=None, base_url=None,
        )


def test_factory_voyage_missing_api_key() -> None:
    with pytest.raises(ValueError, match="voyage requires api_key"):
        make_rerank_provider(
            provider="voyage", model="m", api_key=None, base_url=None,
        )


def test_factory_ollama_missing_base_url() -> None:
    with pytest.raises(ValueError, match="ollama requires base_url"):
        make_rerank_provider(
            provider="ollama", model="m", api_key=None, base_url=None,
        )
```

- [ ] **Step 2: Run rouge**

```bash
uv run pytest tests/unit/rerank/test_factory.py -v
```
Expected : 7 FAIL.

- [ ] **Step 3: Implémenter la factory**

`backend/src/rag/rerank/providers/factory.py` :

```python
from __future__ import annotations

from rag.rerank.protocol import RerankProvider
from rag.rerank.providers.cohere import CohereRerankProvider
from rag.rerank.providers.ollama import OllamaRerankProvider
from rag.rerank.providers.voyage import VoyageRerankProvider


def make_rerank_provider(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
) -> RerankProvider:
    """Factory d'instances `RerankProvider` selon le triplet (provider, key, url)."""
    if provider == "cohere":
        if not api_key:
            raise ValueError("cohere requires api_key")
        return CohereRerankProvider(model=model, api_key=api_key)
    if provider == "voyage":
        if not api_key:
            raise ValueError("voyage requires api_key")
        return VoyageRerankProvider(model=model, api_key=api_key)
    if provider == "ollama":
        if not base_url:
            raise ValueError("ollama requires base_url")
        return OllamaRerankProvider(model=model, base_url=base_url)
    raise ValueError(f"unknown rerank provider: {provider}")
```

- [ ] **Step 4: Run vert**

```bash
uv run pytest tests/unit/rerank/test_factory.py -v
```
Expected : 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/rag/rerank/providers/factory.py \
        backend/tests/unit/rerank/test_factory.py
git commit -m "feat(M8-T6): factory make_rerank_provider + 7 tests"
```

---

## Task 7: Service rerank_configs (get/upsert/delete) + tests intégration

**Files:**
- Create: `backend/src/rag/services/rerank_configs.py`
- Create: `backend/tests/integration/test_services_rerank_configs.py`

**Contexte** : Le service réplique le pattern `services/workspaces.py` (validation eager via `_validate_ref_via_vault`). L'eager validation est faite côté service, pas dans la dépendance FastAPI.

- [ ] **Step 1: Écrire les tests (rouge)**

`backend/tests/integration/test_services_rerank_configs.py` :

```python
from __future__ import annotations

from hashlib import sha256
from typing import Any

import asyncpg
import pytest

from rag.schemas.admin import RerankSpec
from rag.services.rerank_configs import (
    delete_rerank_config,
    get_rerank_config,
    upsert_rerank_config,
)
from tests.integration._workspace_seed import seed_workspace


class _StubResolver:
    """Resolver factice : accept tout, never raises."""

    async def resolve_with_retry(self, ref: str) -> str:
        return "stubbed-secret-value"


class _FailingResolver:
    async def resolve_with_retry(self, ref: str) -> str:
        raise RuntimeError(f"vault ref not found: {ref}")


@pytest.fixture
async def workspace_id(migrated: asyncpg.Pool) -> str:
    async with migrated.acquire() as conn:
        return await seed_workspace(conn, name="ws_rerank")


@pytest.mark.asyncio
async def test_get_returns_none_when_no_config(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    cfg = await get_rerank_config(workspace_id, migrated)
    assert cfg is None


@pytest.mark.asyncio
async def test_upsert_inserts_new_config(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    spec = RerankSpec(
        provider="cohere", model="rerank-v3.5",
        api_key_ref="cohere_key", base_url=None, top_k_pre_rerank=50,
    )
    cfg = await upsert_rerank_config(
        workspace_id=workspace_id, spec=spec,
        config_pool=migrated, resolver=_StubResolver(), default_vault_name="rag",
    )
    assert cfg["provider"] == "cohere"
    assert cfg["model"] == "rerank-v3.5"
    assert cfg["api_key_ref"] == "cohere_key"
    assert cfg["top_k_pre_rerank"] == 50


@pytest.mark.asyncio
async def test_upsert_updates_existing(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    spec1 = RerankSpec(provider="cohere", model="rerank-v3.5",
                       api_key_ref="k1", base_url=None, top_k_pre_rerank=50)
    spec2 = RerankSpec(provider="voyage", model="rerank-2",
                       api_key_ref="k2", base_url=None, top_k_pre_rerank=100)
    await upsert_rerank_config(workspace_id=workspace_id, spec=spec1,
                               config_pool=migrated, resolver=_StubResolver(),
                               default_vault_name="rag")
    cfg = await upsert_rerank_config(workspace_id=workspace_id, spec=spec2,
                                     config_pool=migrated, resolver=_StubResolver(),
                                     default_vault_name="rag")
    assert cfg["provider"] == "voyage"
    assert cfg["model"] == "rerank-2"
    assert cfg["top_k_pre_rerank"] == 100


@pytest.mark.asyncio
async def test_upsert_eager_validates_api_key_ref(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    """Si la ref Harpocrate n'est pas résolvable, upsert lève."""
    spec = RerankSpec(provider="cohere", model="rerank-v3.5",
                     api_key_ref="bad_ref", base_url=None, top_k_pre_rerank=50)
    with pytest.raises(RuntimeError, match="vault ref not found"):
        await upsert_rerank_config(workspace_id=workspace_id, spec=spec,
                                    config_pool=migrated, resolver=_FailingResolver(),
                                    default_vault_name="rag")
    # Vérifie qu'aucune row n'a été créée
    cfg = await get_rerank_config(workspace_id, migrated)
    assert cfg is None


@pytest.mark.asyncio
async def test_upsert_skips_validation_if_no_api_key_ref(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    """Ollama : api_key_ref None → pas d'appel resolver (Failing ne lève donc pas)."""
    spec = RerankSpec(provider="ollama", model="bge",
                     api_key_ref=None, base_url="http://localhost:11434",
                     top_k_pre_rerank=50)
    cfg = await upsert_rerank_config(workspace_id=workspace_id, spec=spec,
                                     config_pool=migrated, resolver=_FailingResolver(),
                                     default_vault_name="rag")
    assert cfg["provider"] == "ollama"


@pytest.mark.asyncio
async def test_delete_removes_config(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    spec = RerankSpec(provider="cohere", model="rerank-v3.5",
                     api_key_ref="k", base_url=None, top_k_pre_rerank=50)
    await upsert_rerank_config(workspace_id=workspace_id, spec=spec,
                               config_pool=migrated, resolver=_StubResolver(),
                               default_vault_name="rag")
    await delete_rerank_config(workspace_id, migrated)
    cfg = await get_rerank_config(workspace_id, migrated)
    assert cfg is None


@pytest.mark.asyncio
async def test_delete_idempotent_when_absent(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    """Pas d'erreur si la config n'existe pas."""
    await delete_rerank_config(workspace_id, migrated)  # ne lève pas
```

- [ ] **Step 2: Run rouge**

```bash
uv run pytest tests/integration/test_services_rerank_configs.py -v
```
Expected : 7 FAIL.

- [ ] **Step 3: Implémenter le service**

`backend/src/rag/services/rerank_configs.py` :

```python
from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

import asyncpg
import structlog

from rag.schemas.admin import RerankSpec
from rag.secrets.references import build_ref

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


def _to_vault_ref(logical_key: str, vault_name: str) -> str:
    return build_ref(vault_name, logical_key)


async def get_rerank_config(
    workspace_id: UUID | str,
    config_pool: asyncpg.Pool,
) -> dict[str, Any] | None:
    """Retourne la config rerank du workspace ou None si absente."""
    row = await config_pool.fetchrow(
        """
        SELECT workspace_id, provider, model, base_url, api_key_ref,
               top_k_pre_rerank, created_at, updated_at
        FROM rerank_configs
        WHERE workspace_id = $1
        """,
        workspace_id,
    )
    return dict(row) if row is not None else None


async def upsert_rerank_config(
    *,
    workspace_id: UUID | str,
    spec: RerankSpec,
    config_pool: asyncpg.Pool,
    resolver: _ResolverProtocol,
    default_vault_name: str,
) -> dict[str, Any]:
    """Insert ou update la config rerank. Validation eager api_key_ref si défini.

    Lève l'exception du resolver si la ref n'est pas résolvable (aucune row écrite).
    """
    if spec.api_key_ref:
        # Eager validation : si la ref n'est pas résolvable, on lève AVANT d'écrire.
        await resolver.resolve_with_retry(
            _to_vault_ref(spec.api_key_ref, default_vault_name)
        )

    row = await config_pool.fetchrow(
        """
        INSERT INTO rerank_configs
            (workspace_id, provider, model, base_url, api_key_ref, top_k_pre_rerank)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (workspace_id) DO UPDATE
        SET provider = EXCLUDED.provider,
            model = EXCLUDED.model,
            base_url = EXCLUDED.base_url,
            api_key_ref = EXCLUDED.api_key_ref,
            top_k_pre_rerank = EXCLUDED.top_k_pre_rerank,
            updated_at = now()
        RETURNING workspace_id, provider, model, base_url, api_key_ref,
                  top_k_pre_rerank, created_at, updated_at
        """,
        workspace_id, spec.provider, spec.model, spec.base_url,
        spec.api_key_ref, spec.top_k_pre_rerank,
    )
    if row is None:
        raise RuntimeError("unexpected None from RETURNING")
    log.info(
        "rerank.upserted",
        workspace_id=str(workspace_id),
        provider=spec.provider,
        model=spec.model,
    )
    return dict(row)


async def delete_rerank_config(
    workspace_id: UUID | str,
    config_pool: asyncpg.Pool,
) -> None:
    """Idempotent : pas d'erreur si la config n'existe pas."""
    await config_pool.execute(
        "DELETE FROM rerank_configs WHERE workspace_id = $1",
        workspace_id,
    )
    log.info("rerank.deleted", workspace_id=str(workspace_id))
```

**Note import `build_ref`** : vérifier le bon chemin (chercher avec `grep -rn "def build_ref" backend/src/rag/secrets/`). Adapter l'import si nécessaire (l'utilisateur de `_to_vault_ref` dans `services/mcp.py:143` doit donner le bon chemin).

- [ ] **Step 4: Run vert**

```bash
uv run pytest tests/integration/test_services_rerank_configs.py -v
```
Expected : 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/rag/services/rerank_configs.py \
        backend/tests/integration/test_services_rerank_configs.py
git commit -m "feat(M8-T7): service rerank_configs (get/upsert/delete + eager validation)"
```

---

## Task 8: Endpoints admin GET/PUT/DELETE /rerank + tests API

**Files:**
- Modify: `backend/src/rag/api/admin.py`
- Create: `backend/tests/api/test_admin_workspaces_rerank.py`

- [ ] **Step 1: Écrire les tests API (rouge)**

`backend/tests/api/test_admin_workspaces_rerank.py` :

```python
from __future__ import annotations

from fastapi.testclient import TestClient


def _create_workspace(client: TestClient, admin_headers: dict[str, str], name: str) -> None:
    r = client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={
            "name": name,
            "indexer": {
                "provider": "ollama", "model": "mxbai-embed-large",
                "api_key_ref": None,
            },
        },
    )
    assert r.status_code == 201, r.text


def test_get_rerank_returns_404_when_not_configured(
    admin_client: TestClient, admin_headers: dict[str, str],
) -> None:
    _create_workspace(admin_client, admin_headers, "ws_get_no_rerank")
    r = admin_client.get(
        "/api/admin/workspaces/ws_get_no_rerank/rerank",
        headers=admin_headers,
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "rerank_not_configured"


def test_get_rerank_returns_404_when_workspace_missing(
    admin_client: TestClient, admin_headers: dict[str, str],
) -> None:
    r = admin_client.get(
        "/api/admin/workspaces/no_such_ws/rerank",
        headers=admin_headers,
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "workspace_not_found"


def test_put_rerank_creates_config(
    admin_client: TestClient, admin_headers: dict[str, str],
) -> None:
    _create_workspace(admin_client, admin_headers, "ws_put_rerank")
    r = admin_client.put(
        "/api/admin/workspaces/ws_put_rerank/rerank",
        headers=admin_headers,
        json={
            "provider": "ollama", "model": "bge-reranker-v2-m3",
            "api_key_ref": None, "base_url": "http://localhost:11434",
            "top_k_pre_rerank": 50,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "ollama"
    assert body["top_k_pre_rerank"] == 50


def test_put_rerank_upsert_idempotent(
    admin_client: TestClient, admin_headers: dict[str, str],
) -> None:
    _create_workspace(admin_client, admin_headers, "ws_idem_rerank")
    payload = {
        "provider": "ollama", "model": "bge",
        "api_key_ref": None, "base_url": "http://localhost:11434",
        "top_k_pre_rerank": 50,
    }
    r1 = admin_client.put(
        "/api/admin/workspaces/ws_idem_rerank/rerank",
        headers=admin_headers, json=payload,
    )
    r2 = admin_client.put(
        "/api/admin/workspaces/ws_idem_rerank/rerank",
        headers=admin_headers, json={**payload, "top_k_pre_rerank": 100},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["top_k_pre_rerank"] == 100


def test_delete_rerank_204(
    admin_client: TestClient, admin_headers: dict[str, str],
) -> None:
    _create_workspace(admin_client, admin_headers, "ws_del_rerank")
    admin_client.put(
        "/api/admin/workspaces/ws_del_rerank/rerank",
        headers=admin_headers,
        json={
            "provider": "ollama", "model": "bge",
            "api_key_ref": None, "base_url": "http://localhost:11434",
            "top_k_pre_rerank": 50,
        },
    )
    r = admin_client.delete(
        "/api/admin/workspaces/ws_del_rerank/rerank",
        headers=admin_headers,
    )
    assert r.status_code == 204


def test_delete_rerank_idempotent_when_absent(
    admin_client: TestClient, admin_headers: dict[str, str],
) -> None:
    _create_workspace(admin_client, admin_headers, "ws_del_absent")
    r = admin_client.delete(
        "/api/admin/workspaces/ws_del_absent/rerank",
        headers=admin_headers,
    )
    assert r.status_code == 204
```

- [ ] **Step 2: Run rouge**

```bash
uv run pytest tests/api/test_admin_workspaces_rerank.py -v
```
Expected : 6 FAIL (endpoints absents).

- [ ] **Step 3: Ajouter les 3 endpoints dans `admin.py`**

Dans `backend/src/rag/api/admin.py`, dans `build_admin_router()`, ajouter (après les endpoints workspace existants) :

```python
# ─── Rerank configs ─────────────────────────────────────────────────────

@router.get("/workspaces/{name}/rerank")
async def get_rerank_endpoint(name: str, request: Request) -> RerankConfigResponse:
    """Retourne la config rerank du workspace.

    404 `workspace_not_found` si le workspace n'existe pas.
    404 `rerank_not_configured` si le workspace existe mais sans rerank.
    """
    ws_row = await _config_pool(request).fetchrow(
        "SELECT id FROM workspaces WHERE name = $1", name,
    )
    if ws_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace_not_found",
        )
    from rag.services.rerank_configs import get_rerank_config
    cfg = await get_rerank_config(ws_row["id"], _config_pool(request))
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="rerank_not_configured",
        )
    return RerankConfigResponse(
        workspace_id=cfg["workspace_id"],
        provider=cfg["provider"], model=cfg["model"],
        api_key_ref=cfg["api_key_ref"], base_url=cfg["base_url"],
        top_k_pre_rerank=cfg["top_k_pre_rerank"],
        created_at=cfg["created_at"].isoformat(),
        updated_at=cfg["updated_at"].isoformat(),
    )


@router.put("/workspaces/{name}/rerank")
async def put_rerank_endpoint(
    name: str, payload: RerankSpec, request: Request,
) -> RerankConfigResponse:
    """Upsert la config rerank du workspace. Validation eager api_key_ref."""
    ws_row = await _config_pool(request).fetchrow(
        "SELECT id FROM workspaces WHERE name = $1", name,
    )
    if ws_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace_not_found",
        )
    from rag.services.rerank_configs import upsert_rerank_config
    cfg = await upsert_rerank_config(
        workspace_id=ws_row["id"], spec=payload,
        config_pool=_config_pool(request),
        resolver=_resolver(request),
        default_vault_name=await _resolve_default_vault_or_503(request),
    )
    return RerankConfigResponse(
        workspace_id=cfg["workspace_id"],
        provider=cfg["provider"], model=cfg["model"],
        api_key_ref=cfg["api_key_ref"], base_url=cfg["base_url"],
        top_k_pre_rerank=cfg["top_k_pre_rerank"],
        created_at=cfg["created_at"].isoformat(),
        updated_at=cfg["updated_at"].isoformat(),
    )


@router.delete(
    "/workspaces/{name}/rerank",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_rerank_endpoint(name: str, request: Request) -> Response:
    """Supprime la config rerank. Idempotent : 204 même si absente."""
    ws_row = await _config_pool(request).fetchrow(
        "SELECT id FROM workspaces WHERE name = $1", name,
    )
    if ws_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace_not_found",
        )
    from rag.services.rerank_configs import delete_rerank_config
    await delete_rerank_config(ws_row["id"], _config_pool(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

Ajouter les imports en tête de `admin.py` (à côté des autres schemas) :

```python
from rag.schemas.admin import RerankConfigResponse, RerankSpec
```

- [ ] **Step 4: Run vert**

```bash
uv run pytest tests/api/test_admin_workspaces_rerank.py -v
```
Expected : 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/rag/api/admin.py \
        backend/tests/api/test_admin_workspaces_rerank.py
git commit -m "feat(M8-T8): endpoints admin GET/PUT/DELETE /workspaces/{name}/rerank"
```

---

## Task 9: Intégration `_load_workspace_context` + `_search_one` + rerank_factory injectable

**Files:**
- Modify: `backend/src/rag/services/mcp.py`
- Modify: `backend/src/rag/api/mcp.py`

- [ ] **Step 1: Étendre `_load_workspace_context`**

Dans `backend/src/rag/services/mcp.py:104-131`, remplacer la fonction par :

```python
async def _load_workspace_context(
    config_pool: asyncpg.Pool,
    name: str,
) -> dict[str, Any]:
    """Charge provider+model+api_key_ref+base_url+rag_cnx pour un workspace.

    Charge aussi la config rerank (LEFT JOIN). Si rerank_configs n'a pas de row,
    le dict retourné contient `rerank=None`. Sinon contient
    `rerank={provider, model, api_key_ref, base_url, top_k_pre_rerank}`.
    """
    row = await config_pool.fetchrow(
        """
        SELECT
            w.name AS workspace_name,
            w.rag_cnx AS rag_cnx,
            ic.provider AS provider,
            ic.model AS model,
            ic.api_key_ref AS api_key_ref,
            ic.base_url AS base_url,
            rc.provider AS rerank_provider,
            rc.model AS rerank_model,
            rc.api_key_ref AS rerank_api_key_ref,
            rc.base_url AS rerank_base_url,
            rc.top_k_pre_rerank AS rerank_top_k_pre_rerank
        FROM workspaces w
        JOIN indexer_configs ic ON ic.workspace_id = w.id
        LEFT JOIN rerank_configs rc ON rc.workspace_id = w.id
        WHERE w.name = $1
        """,
        name,
    )
    if row is None:
        raise RuntimeError(f"workspace {name!r} disappeared between auth and load")
    ctx = dict(row)
    if ctx["rerank_provider"] is not None:
        ctx["rerank"] = {
            "provider": ctx["rerank_provider"],
            "model": ctx["rerank_model"],
            "api_key_ref": ctx["rerank_api_key_ref"],
            "base_url": ctx["rerank_base_url"],
            "top_k_pre_rerank": ctx["rerank_top_k_pre_rerank"],
        }
    else:
        ctx["rerank"] = None
    # Cleanup : retirer les clés intermédiaires
    for k in ("rerank_provider", "rerank_model", "rerank_api_key_ref",
              "rerank_base_url", "rerank_top_k_pre_rerank"):
        ctx.pop(k, None)
    return ctx
```

- [ ] **Step 2: Étendre `search()` et `_search_one()` signatures**

Modifier `search()` (`services/mcp.py:155`) pour accepter un `rerank_factory` optionnel :

```python
from rag.rerank.providers.factory import make_rerank_provider as _make_rerank_default
from rag.rerank.protocol import RerankProvider

async def search(
    *,
    refs: list[McpWorkspaceRef],
    query: str,
    top_k: int,
    min_score: float,
    config_pool: asyncpg.Pool,
    pool_registry: WorkspacePoolRegistry,
    apikey_cache: ApiKeyCache,
    api_key_dek: str,
    secret_resolver: _ResolverProtocol,
    default_vault_name: str = "rag",
    provider_factory: Callable[..., EmbeddingProvider] | None = None,
    rerank_factory: Callable[..., RerankProvider] | None = None,
) -> list[SearchHit]:
    factory = provider_factory if provider_factory is not None else make_provider
    rfactory = rerank_factory if rerank_factory is not None else _make_rerank_default
    tasks = [
        _search_one(
            ref=r, query=query, top_k=top_k, min_score=min_score,
            config_pool=config_pool, pool_registry=pool_registry,
            apikey_cache=apikey_cache, api_key_dek=api_key_dek,
            secret_resolver=secret_resolver, default_vault_name=default_vault_name,
            provider_factory=factory, rerank_factory=rfactory,
        )
        for r in refs
    ]
    results = await asyncio.gather(*tasks)
    return [hit for ws_result in results for hit in ws_result.hits]
```

Et `_search_one()` accepte `rerank_factory` et applique le rerank conditionnel après `vector_search`. Code complet à insérer après le `vector_search` existant :

```python
async def _search_one(
    *,
    ref: McpWorkspaceRef,
    query: str,
    top_k: int,
    min_score: float,
    config_pool: asyncpg.Pool,
    pool_registry: WorkspacePoolRegistry,
    apikey_cache: ApiKeyCache,
    api_key_dek: str,
    secret_resolver: _ResolverProtocol,
    default_vault_name: str,
    provider_factory: Callable[..., EmbeddingProvider],
    rerank_factory: Callable[..., RerankProvider],
) -> _WorkspaceResult:
    auth = await _authenticate(ref=ref, config_pool=config_pool, apikey_cache=apikey_cache, api_key_dek=api_key_dek)
    ctx = await _load_workspace_context(config_pool, ref.name)

    api_key: str | None = None
    if ctx["api_key_ref"]:
        api_key = await secret_resolver.resolve_with_retry(
            _to_vault_ref(ctx["api_key_ref"], default_vault_name)
        )

    provider = provider_factory(
        provider=ctx["provider"], model=ctx["model"],
        api_key=api_key, base_url=ctx["base_url"],
    )
    query_vec = await provider.embed_query(query)

    rerank_cfg = ctx.get("rerank")
    pre_top_k = max(top_k, rerank_cfg["top_k_pre_rerank"]) if rerank_cfg else top_k

    ws_pool = await pool_registry.get_workspace_pool(ref.name, ctx["rag_cnx"])
    hits = await vector_search(
        ws_pool, query_vec=query_vec, top_k=pre_top_k, min_score=min_score,
        workspace_name=ref.name, indexer_used=auth.indexer_used,
    )

    # Rerank conditionnel : config présente + > 1 hit (singleton skip)
    if rerank_cfg and len(hits) > 1:
        rerank_api_key: str | None = None
        if rerank_cfg["api_key_ref"]:
            rerank_api_key = await secret_resolver.resolve_with_retry(
                _to_vault_ref(rerank_cfg["api_key_ref"], default_vault_name)
            )
        reranker = rerank_factory(
            provider=rerank_cfg["provider"], model=rerank_cfg["model"],
            api_key=rerank_api_key, base_url=rerank_cfg["base_url"],
        )
        documents = [h.content for h in hits]
        indices = await reranker.rerank(query=query, documents=documents, top_k=top_k)
        hits = [hits[i] for i in indices]
        log.info(
            "mcp.rerank.applied",
            workspace=ref.name, pre_hits=len(documents), post_hits=len(hits),
            provider=rerank_cfg["provider"], model=rerank_cfg["model"],
        )
    elif rerank_cfg:
        log.debug(
            "mcp.rerank.skipped_singleton_or_empty",
            workspace=ref.name, hits=len(hits),
        )

    log.info(
        "mcp.search.workspace_done",
        workspace=ref.name, hits=len(hits), indexer=auth.indexer_used,
    )
    return _WorkspaceResult(
        workspace_name=ref.name, indexer_used=auth.indexer_used,
        hits=hits[:top_k],
    )
```

**Note** : la signature `_search_one()` change (ajout `rerank_factory`). L'appelant `search()` doit déjà passer ce kwarg (cf. step 2 ci-dessus).

- [ ] **Step 3: Vérifier l'appelant `api/mcp.py`**

```bash
grep -n "rerank_factory\|provider_factory" backend/src/rag/api/mcp.py
```

Si `api/mcp.py` appelle `search()` sans kwarg explicite, le default `None` joue → comportement par défaut OK. Pas de modif nécessaire. Sinon adapter.

- [ ] **Step 4: Smoke unit (tests existants doivent rester verts)**

```bash
cd backend
uv run pytest tests/unit/services/test_mcp_search.py tests/unit/services/test_mcp_auth.py -v
```

Expected : tous verts (le rerank par défaut est `None` → workspaces sans rerank inchangés).

- [ ] **Step 5: Commit**

```bash
git add backend/src/rag/services/mcp.py backend/src/rag/api/mcp.py
git commit -m "feat(M8-T9): intégration rerank per-workspace dans _search_one (opt-in)"
```

---

## Task 10: Tests E2E MCP avec rerank + fail-fast

**Files:**
- Create: `backend/tests/integration/test_mcp_with_rerank.py`
- Create: `backend/tests/integration/test_mcp_rerank_fail_fast.py`

- [ ] **Step 1: Écrire `test_mcp_with_rerank.py`**

```python
from __future__ import annotations

from hashlib import sha256
from typing import Any
from unittest.mock import AsyncMock

import asyncpg
import pytest

from rag.services.mcp import search
from tests.integration._workspace_seed import seed_workspace

# ... fixtures helper à adapter aux fixtures existantes dans tests/integration ...

# Pattern attendu : 3 tests
# 1) Workspace AVEC rerank configuré → ordre rerank appliqué
#    - Mock embed_query + vector_search retournent 3 hits
#    - Mock rerank_factory → reranker qui retourne indices [2, 0, 1]
#    - Vérifier que search renvoie les hits dans cet ordre
#
# 2) Workspace SANS rerank → ordre pgvector préservé (comportement actuel)
#    - Pas de row dans rerank_configs
#    - Vérifier que reranker n'est jamais appelé (AsyncMock.assert_not_called())
#
# 3) Singleton hit + workspace AVEC rerank → skip rerank
#    - vector_search retourne 1 seul hit
#    - Vérifier que reranker n'est pas appelé
```

**Code de test attendu** : reprendre le pattern de `tests/integration/test_mcp_*.py` existants pour les fixtures (`session_pool`, `apikey_cache`, etc.), seeder un workspace avec `seed_workspace` (M5e helper), puis pour les tests qui ont besoin du rerank, ajouter `INSERT INTO rerank_configs ...` manuel. Mock `provider_factory` et `rerank_factory` via les kwargs de `search()`.

L'engineer doit lire `tests/integration/test_mcp_auth.py` ou similaire pour comprendre comment les tests intègrent le pool + l'auth + le DEK. Pattern à reproduire.

- [ ] **Step 2: Écrire `test_mcp_rerank_fail_fast.py`**

```python
from __future__ import annotations

import pytest

from rag.rerank.protocol import RerankProviderUnreachable
from rag.services.mcp import search
# ... imports/fixtures ...


@pytest.mark.asyncio
async def test_rerank_provider_unreachable_propagates(...):
    """Si le reranker lève RerankProviderUnreachable, search() lève aussi
    (asyncio.gather propage la première exception)."""

    def failing_rerank_factory(**kwargs):
        class _Failing:
            async def rerank(self, *, query, documents, top_k):
                raise RerankProviderUnreachable("cohere 503")
        return _Failing()

    # ... seed workspace + INSERT rerank_configs ...

    with pytest.raises(RerankProviderUnreachable):
        await search(
            refs=[...], query="q", top_k=5, min_score=0.0,
            config_pool=..., pool_registry=..., apikey_cache=...,
            api_key_dek=..., secret_resolver=...,
            provider_factory=fake_provider_factory,
            rerank_factory=failing_rerank_factory,
        )
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/integration/test_mcp_with_rerank.py tests/integration/test_mcp_rerank_fail_fast.py -v
```
Expected : tous PASS.

Si difficultés à composer les fixtures (pool registry, etc.), s'inspirer du fichier `tests/integration/test_mcp_*` existant le plus proche. Si la complexité de mock est élevée, accepter un test moins exhaustif (1 cas par fichier suffit pour le PR mais on vise idéalement 3+1 cas).

- [ ] **Step 4: Smoke complet**

```bash
uv run pytest tests/ -v 2>&1 | tail -30
```

Vérifier qu'aucun test existant n'a régressé. Acceptable : les 2 fails pré-existants hors M8 (`test_mcp_single_returns_top_k_hits`, `test_push_returns_404_for_unknown_workspace`) listés en M5e.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/integration/test_mcp_with_rerank.py \
        backend/tests/integration/test_mcp_rerank_fail_fast.py
git commit -m "test(M8-T10): E2E rerank (avec/sans config, singleton skip, fail-fast)"
```

---

## Task 11: Doc roadmap + `.env.example`

**Files:**
- Modify: `specs/09-roadmap.md`
- Modify: `backend/.env.example` (ou `.env.example` racine — vérifier où il est)

- [ ] **Step 1: Mettre à jour `specs/09-roadmap.md`**

Dans la section "Reranking" (lignes 41-46), remplacer la liste à puces "Cohere/Voyage/Ollama" par une note de livraison :

```markdown
### Reranking

✅ Livré en M8 — cf. `docs/superpowers/specs/2026-05-17-M8-backend-reranking-design.md`.

Config par workspace (table `rerank_configs`), 3 providers :
- Cohere Rerank API
- Voyage AI Rerank
- Ollama local (BGE / Jina)

Fail-fast si le provider tombe (cohérent avec `mcp.py`).

Frontend (onglet "Rerank" dans WorkspaceDetailPanel) → jalon M8b à venir.
```

- [ ] **Step 2: Documenter dans `.env.example`**

Trouver le fichier `.env.example` à jour :

```bash
ls -la .env.example backend/.env.example 2>/dev/null
```

Ajouter une section après les variables Harpocrate / indexer existantes :

```
# ─── Reranking (M8) ──────────────────────────────────────────────────────────
#
# Les clés API des providers de reranking (Cohere / Voyage) sont stockées
# dans Harpocrate, jamais en `.env`. La table `rerank_configs` référence
# une `api_key_ref` (clé logique Harpocrate) par workspace.
#
# Ollama : pas d'api_key, juste un `base_url` (ex. http://localhost:11434).
#
# Aucune variable d'env spécifique au rerank côté serveur — tout est
# configuré via PUT /api/admin/workspaces/{name}/rerank.
```

- [ ] **Step 3: Commit**

```bash
git add specs/09-roadmap.md backend/.env.example
# adapter le path .env.example selon ce que renvoie le ls
git commit -m "docs(M8-T11): roadmap marque M8 livré + note rerank dans .env.example"
```

---

## Auto-revue post-rédaction

**1. Spec coverage :**
- Spec §3 schéma BDD → T1.
- Spec §4 architecture providers → T2 (protocol) + T3/T4/T5 (3 providers) + T6 (factory).
- Spec §5 intégration MCP → T9 (mcp.py modifié) + T10 (tests E2E).
- Spec §6 API admin → T8 (3 endpoints).
- Spec §7 tests → couverts par chaque tâche, plus T10 E2E.
- Spec §8 plan d'attaque → 11 tâches, aligné avec § 8 du spec.
- Spec §9 hors-scope (frontend, cache, métriques) → respecté.

**2. Placeholder scan :**
- T10 contient deux blocs "Code de test attendu" / "Pattern attendu" avec instructions narratives plutôt que code complet. Justifié : les fixtures d'intégration MCP sont nombreuses et complexes — donner le code complet sans contexte des fixtures réelles produirait du code non-fonctionnel. L'engineer doit lire `test_mcp_auth.py` ou similaire. **À accepter** : c'est mécanique mais demande de l'exploration locale.
- Tout le reste : code complet, commandes exactes, expected outputs.

**3. Type consistency :**
- `RerankProvider`, `RerankAuthError`, `RerankRateLimited`, `RerankProviderUnreachable` cohérents Tasks 2-10.
- `RerankSpec`, `RerankConfigResponse` cohérents Tasks 1, 7, 8.
- `rerank_factory: Callable[..., RerankProvider]` cohérent Tasks 9, 10.
- `_load_workspace_context()` retourne `ctx["rerank"]: dict | None` ; consommé en T9 par `_search_one`.

Risque résiduel : import `build_ref` dans `services/rerank_configs.py` (T7) — chemin à vérifier (`grep -rn "def build_ref" backend/src/rag/secrets/`). Si l'import diffère de `rag.secrets.references`, adapter.
