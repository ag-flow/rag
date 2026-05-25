# M4b — API Push Synchrone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exposer `POST /workspaces/{name}/index` (push synchrone d'un document dans pgvector) avec auth api_key workspace + cache LRU, en réutilisant le `RealIndexer` (M4a) sans dupliquer le pipeline d'embedding.

**Architecture:** Une dependency FastAPI valide l'api_key workspace (lookup DB + bcrypt verify, cachés en LRU TTL 5 min) et retourne un `AuthContext`. Un service `push_document` pré-déduplique sur `indexed_documents.content_hash` puis délègue à `indexer.index_file(...)`. Trois nouveaux modules (`auth/workspace_auth.py`, `api/workspace.py`, `services/push.py`, `schemas/workspace.py`), trois modifs ciblées (`api/errors.py`, `services/workspaces.py`, `main.py`).

**Tech Stack:** FastAPI dependency injection, Pydantic v2 discriminated unions, `bcrypt` (déjà M2), `collections.OrderedDict` pour le LRU, pytest + httpx TestClient pour les tests.

---

## File Structure

| Fichier | Statut | Responsabilité |
|---|---|---|
| `backend/src/rag/auth/workspace_auth.py` | **Create** | `ApiKeyCache` (LRU+TTL), `_CacheEntry`, `AuthContext`, `require_workspace_apikey` dependency |
| `backend/src/rag/schemas/workspace.py` | **Create** | `PushRequest`, `PushIndexedResponse`, `PushSkippedResponse`, `PushResponse` (discriminated union) |
| `backend/src/rag/services/push.py` | **Create** | `normalize_path`, `push_document` orchestration |
| `backend/src/rag/api/workspace.py` | **Create** | `build_workspace_router()` exposant `POST /workspaces/{name}/index` |
| `backend/src/rag/api/errors.py` | **Modify** | Ajouter `InvalidPath`, `ContentTooLarge`, `EmbeddingProviderUnavailable` |
| `backend/src/rag/services/workspaces.py` | **Modify** | `rotate_apikey()` accepte `apikey_cache: ApiKeyCache \| None` et invalide |
| `backend/src/rag/api/admin.py` | **Modify** | `rotate_apikey_endpoint` passe `app.state.apikey_cache` |
| `backend/src/rag/main.py` | **Modify** | Instancie cache, expose `app.state.indexer`, include workspace router |
| `backend/tests/unit/auth/test_workspace_auth_cache.py` | **Create** | Tests unitaires `ApiKeyCache` |
| `backend/tests/unit/services/test_push_path_normalize.py` | **Create** | Tests unitaires `normalize_path` |
| `backend/tests/unit/schemas/test_workspace_dto.py` | **Create** | Tests unitaires DTOs |
| `backend/tests/unit/services/test_push_service.py` | **Create** | Tests unitaires `push_document` (mock indexer + pool) |
| `backend/tests/api/test_workspace_push_auth.py` | **Create** | Tests integration auth (404, 401, 200, cache, rotate invalidation) |
| `backend/tests/api/test_workspace_push_dedup.py` | **Create** | Tests integration dedup |
| `backend/tests/api/test_workspace_push_errors.py` | **Create** | Tests integration codes erreur (422, 413) |
| `backend/tests/smoke/test_push_e2e_ollama.py` | **Create** | Smoke opt-in Ollama (e2e push + pgvector check) |

---

## Task 1: ApiKeyCache (LRU + TTL)

**Files:**
- Create: `backend/src/rag/auth/workspace_auth.py`
- Create: `backend/tests/unit/auth/__init__.py` (empty)
- Create: `backend/tests/unit/auth/test_workspace_auth_cache.py`

- [ ] **Step 1: Créer le test unitaire LRU+TTL**

```python
# backend/tests/unit/auth/test_workspace_auth_cache.py
from __future__ import annotations

import time
from uuid import uuid4

import pytest

from rag.auth.workspace_auth import ApiKeyCache, _CacheEntry


def _entry() -> _CacheEntry:
    return _CacheEntry(
        workspace_id=uuid4(),
        indexer_used="openai/text-embedding-3-small",
        inserted_at=time.monotonic(),
    )


def test_get_returns_none_on_miss() -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    assert cache.get("ws", "key") is None


def test_put_then_get_returns_entry() -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    e = _entry()
    cache.put("ws", "key", e)
    got = cache.get("ws", "key")
    assert got is e


def test_ttl_expired_returns_none() -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    stale = _CacheEntry(
        workspace_id=uuid4(),
        indexer_used="openai/m",
        inserted_at=time.monotonic() - 120,
    )
    cache.put("ws", "key", stale)
    assert cache.get("ws", "key") is None


def test_lru_eviction_when_over_capacity() -> None:
    cache = ApiKeyCache(max_size=2, ttl_seconds=60)
    e1 = _entry()
    e2 = _entry()
    e3 = _entry()
    cache.put("ws", "k1", e1)
    cache.put("ws", "k2", e2)
    cache.put("ws", "k3", e3)  # évincte k1 (le plus ancien)
    assert cache.get("ws", "k1") is None
    assert cache.get("ws", "k2") is e2
    assert cache.get("ws", "k3") is e3


def test_get_promotes_entry_to_most_recent() -> None:
    cache = ApiKeyCache(max_size=2, ttl_seconds=60)
    e1 = _entry()
    e2 = _entry()
    cache.put("ws", "k1", e1)
    cache.put("ws", "k2", e2)
    # accès à k1 le rend le plus récent ; l'insertion suivante doit évincter k2
    assert cache.get("ws", "k1") is e1
    e3 = _entry()
    cache.put("ws", "k3", e3)
    assert cache.get("ws", "k2") is None
    assert cache.get("ws", "k1") is e1


def test_invalidate_removes_only_named_workspace_entries() -> None:
    cache = ApiKeyCache(max_size=8, ttl_seconds=60)
    e_a, e_b = _entry(), _entry()
    cache.put("ws_a", "k", e_a)
    cache.put("ws_b", "k", e_b)
    cache.invalidate("ws_a")
    assert cache.get("ws_a", "k") is None
    assert cache.get("ws_b", "k") is e_b


def test_invalidate_unknown_workspace_is_noop() -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    e = _entry()
    cache.put("ws", "k", e)
    cache.invalidate("unknown_ws")
    assert cache.get("ws", "k") is e
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
cd backend
uv run pytest tests/unit/auth/test_workspace_auth_cache.py -v
```

Expected: `ImportError` or `ModuleNotFoundError: No module named 'rag.auth.workspace_auth'`.

- [ ] **Step 3: Implémenter ApiKeyCache**

```python
# backend/src/rag/auth/workspace_auth.py
from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from uuid import UUID


@dataclass
class _CacheEntry:
    workspace_id: UUID
    indexer_used: str
    inserted_at: float


class ApiKeyCache:
    """Cache LRU+TTL des api_keys workspace validées par bcrypt.

    Clé : (workspace_name, api_key_clair). Valeur : _CacheEntry.

    Le cache ne contient que des entrées dont la vérification bcrypt a réussi.
    Un attaquant qui présente une clé invalide paie bcrypt à chaque tentative,
    sans pollution du cache (LRU évincte tout de toute façon).
    """

    def __init__(self, *, max_size: int = 256, ttl_seconds: int = 300) -> None:
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._store: OrderedDict[tuple[str, str], _CacheEntry] = OrderedDict()

    def get(self, workspace_name: str, api_key: str) -> _CacheEntry | None:
        key = (workspace_name, api_key)
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() - entry.inserted_at > self._ttl_seconds:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return entry

    def put(self, workspace_name: str, api_key: str, entry: _CacheEntry) -> None:
        key = (workspace_name, api_key)
        self._store[key] = entry
        self._store.move_to_end(key)
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def invalidate(self, workspace_name: str) -> None:
        to_delete = [k for k in self._store if k[0] == workspace_name]
        for k in to_delete:
            del self._store[k]
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
uv run pytest tests/unit/auth/test_workspace_auth_cache.py -v
```

Expected: `7 passed`.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/rag/auth/workspace_auth.py backend/tests/unit/auth/__init__.py backend/tests/unit/auth/test_workspace_auth_cache.py
git commit -m "feat(M4b): ApiKeyCache LRU+TTL pour auth workspace"
```

---

## Task 2: AuthContext + require_workspace_apikey dependency

**Files:**
- Modify: `backend/src/rag/auth/workspace_auth.py`
- Create: `backend/tests/unit/auth/test_require_workspace_apikey.py`

- [ ] **Step 1: Écrire les tests de la dependency**

```python
# backend/tests/unit/auth/test_require_workspace_apikey.py
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from rag.auth.workspace_auth import (
    ApiKeyCache,
    AuthContext,
    _CacheEntry,
    require_workspace_apikey,
)


def _fake_request(headers: dict[str, str], pool, cache: ApiKeyCache):
    return SimpleNamespace(
        headers=headers,
        app=SimpleNamespace(
            state=SimpleNamespace(
                apikey_cache=cache,
                pools=SimpleNamespace(config_pool=pool),
            )
        ),
    )


@pytest.mark.asyncio
async def test_missing_authorization_header_raises_401() -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    pool = MagicMock()
    req = _fake_request({}, pool, cache)
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    assert exc.value.detail == "missing_bearer_token"


@pytest.mark.asyncio
async def test_wrong_scheme_raises_401() -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    pool = MagicMock()
    req = _fake_request({"Authorization": "Basic abc"}, pool, cache)
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_auth_scheme"


@pytest.mark.asyncio
async def test_cache_hit_returns_auth_context_without_db() -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    ws_id = uuid4()
    cache.put("ws", "api-key-xyz", _CacheEntry(
        workspace_id=ws_id,
        indexer_used="openai/text-embedding-3-small",
        inserted_at=1.0,
    ))
    # Le _CacheEntry vient d'être inséré, donc inserted_at devra être réécrit
    # juste après par le test pour ne pas être considéré expiré : on inverse.
    # Plus simple : on rouvre une entrée fraîche via _CacheEntry(time.monotonic())
    import time
    cache._store.clear()
    cache.put("ws", "api-key-xyz", _CacheEntry(
        workspace_id=ws_id,
        indexer_used="openai/text-embedding-3-small",
        inserted_at=time.monotonic(),
    ))

    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=AssertionError("pool must not be called on cache hit"))

    req = _fake_request({"Authorization": "Bearer api-key-xyz"}, pool, cache)
    ctx = await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert isinstance(ctx, AuthContext)
    assert ctx.workspace_id == ws_id
    assert ctx.indexer_used == "openai/text-embedding-3-small"


@pytest.mark.asyncio
async def test_cache_miss_workspace_not_found_raises_404() -> None:
    from rag.api.errors import WorkspaceNotFound

    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    req = _fake_request({"Authorization": "Bearer some-key"}, pool, cache)
    with pytest.raises(WorkspaceNotFound):
        await require_workspace_apikey("ghost", req)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_cache_miss_invalid_bcrypt_raises_401(monkeypatch) -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    ws_id = uuid4()
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={
        "id": ws_id,
        "api_key_hash": "$2b$12$invalidhash",
        "indexer_used": "openai/text-embedding-3-small",
    })

    from rag.auth import workspace_auth
    monkeypatch.setattr(workspace_auth, "verify_api_key", lambda _k, _h: False)

    req = _fake_request({"Authorization": "Bearer bad-key"}, pool, cache)
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_workspace_apikey"
    assert cache.get("ws", "bad-key") is None  # mauvaise clé non cachée


@pytest.mark.asyncio
async def test_cache_miss_valid_bcrypt_populates_cache(monkeypatch) -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    ws_id = uuid4()
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={
        "id": ws_id,
        "api_key_hash": "$2b$12$validhash",
        "indexer_used": "voyage/voyage-3-lite",
    })

    from rag.auth import workspace_auth
    monkeypatch.setattr(workspace_auth, "verify_api_key", lambda _k, _h: True)

    req = _fake_request({"Authorization": "Bearer good-key"}, pool, cache)
    ctx = await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert ctx.workspace_id == ws_id
    assert ctx.indexer_used == "voyage/voyage-3-lite"
    cached = cache.get("ws", "good-key")
    assert cached is not None
    assert cached.workspace_id == ws_id
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
uv run pytest tests/unit/auth/test_require_workspace_apikey.py -v
```

Expected: `ImportError: cannot import name 'AuthContext' from 'rag.auth.workspace_auth'`.

- [ ] **Step 3: Étendre `workspace_auth.py`**

Append au fichier `backend/src/rag/auth/workspace_auth.py` :

```python
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import asyncpg
from fastapi import HTTPException, Request, status

from rag.api.errors import WorkspaceNotFound
from rag.services.apikey import verify_api_key

if TYPE_CHECKING:
    pass


@dataclass
class AuthContext:
    workspace_id: UUID
    indexer_used: str


def _extract_bearer(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing_bearer_token",
        )
    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_auth_scheme",
        )
    return parts[1].strip()


async def require_workspace_apikey(
    name: str,
    request: Request,
) -> AuthContext:
    """Dependency FastAPI : valide `Authorization: Bearer <WORKSPACE_API_KEY>`
    contre `workspaces[name].api_key_hash` (bcrypt), avec cache LRU+TTL.

    - 401 si bearer absent / mauvais scheme / clé invalide.
    - 404 si workspace inexistant ou pas d'indexer_config.
    - Sur succès : retourne `AuthContext(workspace_id, indexer_used)`.
    """
    api_key = _extract_bearer(request)

    cache: ApiKeyCache = request.app.state.apikey_cache
    pool: asyncpg.Pool = request.app.state.pools.config_pool

    entry = cache.get(name, api_key)
    if entry is not None:
        return AuthContext(workspace_id=entry.workspace_id, indexer_used=entry.indexer_used)

    row = await pool.fetchrow(
        """
        SELECT w.id, w.api_key_hash,
               ic.provider || '/' || ic.model AS indexer_used
        FROM workspaces w
        JOIN indexer_configs ic ON ic.workspace_id = w.id
        WHERE w.name = $1
        """,
        name,
    )
    if row is None:
        raise WorkspaceNotFound(name)

    if not verify_api_key(api_key, row["api_key_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_workspace_apikey",
        )

    new_entry = _CacheEntry(
        workspace_id=row["id"],
        indexer_used=row["indexer_used"],
        inserted_at=time.monotonic(),
    )
    cache.put(name, api_key, new_entry)
    return AuthContext(workspace_id=row["id"], indexer_used=row["indexer_used"])
```

Au-dessus du fichier, ajouter `from uuid import UUID` aux imports si pas déjà présent.

- [ ] **Step 4: Run test to verify it passes**

```powershell
uv run pytest tests/unit/auth/test_require_workspace_apikey.py -v
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/rag/auth/workspace_auth.py backend/tests/unit/auth/test_require_workspace_apikey.py
git commit -m "feat(M4b): dependency require_workspace_apikey avec cache"
```

---

## Task 3: Schemas — PushRequest + PushResponse discriminated union

**Files:**
- Create: `backend/src/rag/schemas/workspace.py`
- Create: `backend/tests/unit/schemas/__init__.py` (empty si absent)
- Create: `backend/tests/unit/schemas/test_workspace_dto.py`

- [ ] **Step 1: Écrire les tests DTOs**

```python
# backend/tests/unit/schemas/test_workspace_dto.py
from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.schemas.workspace import (
    PushIndexedResponse,
    PushRequest,
    PushSkippedResponse,
)


def test_push_request_accepts_valid_payload() -> None:
    r = PushRequest(path="docs/foo.md", content="# Hello\n")
    assert r.path == "docs/foo.md"
    assert r.content == "# Hello\n"


def test_push_request_rejects_empty_path() -> None:
    with pytest.raises(ValidationError):
        PushRequest(path="", content="x")


def test_push_request_rejects_empty_content() -> None:
    with pytest.raises(ValidationError):
        PushRequest(path="ok.md", content="")


def test_push_request_accepts_content_at_exactly_5mb() -> None:
    content = "a" * (5 * 1024 * 1024)
    r = PushRequest(path="big.md", content=content)
    assert len(r.content) == 5 * 1024 * 1024


def test_push_request_rejects_content_above_5mb() -> None:
    content = "a" * (5 * 1024 * 1024 + 1)
    with pytest.raises(ValidationError) as exc:
        PushRequest(path="too_big.md", content=content)
    assert "content_too_large" in str(exc.value)


def test_push_request_counts_utf8_bytes_not_chars_for_size() -> None:
    # 'é' = 2 bytes UTF-8. 2_750_000 caractères = 5_500_000 bytes > 5 MB.
    content = "é" * (2_750_000)
    with pytest.raises(ValidationError):
        PushRequest(path="utf.md", content=content)


def test_push_request_rejects_path_above_1024_chars() -> None:
    with pytest.raises(ValidationError):
        PushRequest(path="a" * 1025, content="x")


def test_push_indexed_response_serializes_with_status_indexed() -> None:
    r = PushIndexedResponse(path="x.md", chunks=3, hash="sha256:abc")
    d = r.model_dump()
    assert d["status"] == "indexed"
    assert d["chunks"] == 3
    assert d["hash"] == "sha256:abc"


def test_push_skipped_response_serializes_with_status_skipped() -> None:
    r = PushSkippedResponse(path="x.md")
    d = r.model_dump()
    assert d["status"] == "skipped"
    assert d["reason"] == "content_unchanged"
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
uv run pytest tests/unit/schemas/test_workspace_dto.py -v
```

Expected: `ModuleNotFoundError: No module named 'rag.schemas.workspace'`.

- [ ] **Step 3: Implémenter `schemas/workspace.py`**

```python
# backend/src/rag/schemas/workspace.py
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

_PATH_MAX_LEN = 1024
_CONTENT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB UTF-8


class PushRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=_PATH_MAX_LEN)
    content: str = Field(..., min_length=1)

    @field_validator("content")
    @classmethod
    def _content_size(cls, v: str) -> str:
        if len(v.encode("utf-8")) > _CONTENT_MAX_BYTES:
            raise ValueError("content_too_large")
        return v


class PushIndexedResponse(BaseModel):
    path: str
    status: Literal["indexed"] = "indexed"
    chunks: int
    hash: str


class PushSkippedResponse(BaseModel):
    path: str
    status: Literal["skipped"] = "skipped"
    reason: Literal["content_unchanged"] = "content_unchanged"


PushResponse = Annotated[
    PushIndexedResponse | PushSkippedResponse,
    Field(discriminator="status"),
]
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
uv run pytest tests/unit/schemas/test_workspace_dto.py -v
```

Expected: `9 passed`.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/rag/schemas/workspace.py backend/tests/unit/schemas/__init__.py backend/tests/unit/schemas/test_workspace_dto.py
git commit -m "feat(M4b): schemas PushRequest/PushResponse discriminated union"
```

---

## Task 4: Exceptions `InvalidPath`, `ContentTooLarge`, `EmbeddingProviderUnavailable`

**Files:**
- Modify: `backend/src/rag/api/errors.py`
- Create: `backend/tests/unit/api/__init__.py` (empty si absent)
- Create: `backend/tests/unit/api/test_workspace_errors.py`

- [ ] **Step 1: Écrire les tests des nouvelles exceptions**

```python
# backend/tests/unit/api/test_workspace_errors.py
from __future__ import annotations

from rag.api.errors import (
    AdminError,
    ContentTooLarge,
    EmbeddingProviderUnavailable,
    InvalidPath,
)


def test_invalid_path_payload_includes_reason() -> None:
    e = InvalidPath("path_traversal_forbidden")
    assert isinstance(e, AdminError)
    assert e.http_status == 422
    assert e.to_payload() == {
        "error": "invalid_path",
        "reason": "path_traversal_forbidden",
    }


def test_content_too_large_payload_includes_limit() -> None:
    e = ContentTooLarge()
    assert isinstance(e, AdminError)
    assert e.http_status == 413
    assert e.to_payload() == {
        "error": "content_too_large",
        "limit_bytes": 5 * 1024 * 1024,
    }


def test_embedding_provider_unavailable_payload() -> None:
    e = EmbeddingProviderUnavailable("openai", "rate_limited")
    assert isinstance(e, AdminError)
    assert e.http_status == 502
    assert e.to_payload() == {
        "error": "embedding_provider_error",
        "provider": "openai",
        "reason": "rate_limited",
    }
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
uv run pytest tests/unit/api/test_workspace_errors.py -v
```

Expected: `ImportError: cannot import name 'InvalidPath' from 'rag.api.errors'`.

- [ ] **Step 3: Ajouter les exceptions à `api/errors.py`**

Append, juste avant `def register_error_handlers(app: FastAPI)` :

```python
class InvalidPath(AdminError):
    http_status = 422

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def to_payload(self) -> dict[str, object]:
        return {"error": "invalid_path", "reason": self.reason}


class ContentTooLarge(AdminError):
    http_status = 413

    _LIMIT_BYTES = 5 * 1024 * 1024

    def to_payload(self) -> dict[str, object]:
        return {"error": "content_too_large", "limit_bytes": self._LIMIT_BYTES}


class EmbeddingProviderUnavailable(AdminError):
    http_status = 502

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(provider, reason)
        self.provider = provider
        self.reason = reason

    def to_payload(self) -> dict[str, object]:
        return {
            "error": "embedding_provider_error",
            "provider": self.provider,
            "reason": self.reason,
        }
```

Et modifier `register_error_handlers` pour intercepter le `RequestValidationError`
de Pydantic et le remapper en 413 si la cause est `content_too_large` :

```python
def register_error_handlers(app: FastAPI) -> None:
    """Enregistre les handlers d'exceptions JSON globaux."""

    async def _admin_handler(_request: Request, exc: AdminError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_payload())

    app.add_exception_handler(AdminError, _admin_handler)  # type: ignore[arg-type]

    # Remap Pydantic ValidationError(content_too_large) → 413 (au lieu du 422
    # par défaut). Le validator du DTO `PushRequest.content` lève
    # `ValueError("content_too_large")` quand le body UTF-8 dépasse 5 MB ;
    # ce remap aligne la réponse HTTP sur la sémantique RFC 7231 §6.5.11.
    from fastapi.exceptions import RequestValidationError

    async def _validation_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        for err in exc.errors():
            msg = str(err.get("msg") or "")
            if "content_too_large" in msg:
                return JSONResponse(
                    status_code=413,
                    content=ContentTooLarge().to_payload(),
                )
        # Comportement Pydantic par défaut : 422 avec le détail des erreurs.
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
```

**Important** : ce remplace **complètement** la fonction `register_error_handlers` existante (qui contient juste `_handler` pour `AdminError`). Préserver l'enregistrement `AdminError` → `_admin_handler` (renommé pour clarté). Aucune régression : tous les call-sites continuent de lever `AdminError`.

- [ ] **Step 4: Run test to verify it passes**

```powershell
uv run pytest tests/unit/api/test_workspace_errors.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/rag/api/errors.py backend/tests/unit/api/__init__.py backend/tests/unit/api/test_workspace_errors.py
git commit -m "feat(M4b): exceptions InvalidPath/ContentTooLarge/EmbeddingProviderUnavailable"
```

---

## Task 5: `normalize_path` (POSIX strict)

**Files:**
- Create: `backend/src/rag/services/push.py` (partiel — juste `normalize_path` pour cette task)
- Create: `backend/tests/unit/services/test_push_path_normalize.py`

- [ ] **Step 1: Écrire les tests de normalisation**

```python
# backend/tests/unit/services/test_push_path_normalize.py
from __future__ import annotations

import pytest

from rag.api.errors import InvalidPath
from rag.services.push import normalize_path


def test_happy_path_passthrough() -> None:
    assert normalize_path("docs/foo.md") == "docs/foo.md"


def test_windows_backslashes_normalized_to_forward() -> None:
    assert normalize_path("docs\\sub\\foo.md") == "docs/sub/foo.md"


def test_nul_byte_rejected() -> None:
    with pytest.raises(InvalidPath) as exc:
        normalize_path("foo\x00bar")
    assert exc.value.reason == "path_contains_nul"


def test_absolute_path_rejected() -> None:
    with pytest.raises(InvalidPath) as exc:
        normalize_path("/etc/passwd")
    assert exc.value.reason == "path_must_be_relative"


def test_traversal_segment_rejected() -> None:
    with pytest.raises(InvalidPath) as exc:
        normalize_path("foo/../bar")
    assert exc.value.reason == "path_traversal_forbidden"


def test_leading_traversal_rejected() -> None:
    with pytest.raises(InvalidPath) as exc:
        normalize_path("../foo")
    assert exc.value.reason == "path_traversal_forbidden"


def test_trailing_traversal_rejected() -> None:
    with pytest.raises(InvalidPath) as exc:
        normalize_path("foo/..")
    assert exc.value.reason == "path_traversal_forbidden"


def test_empty_after_normalization_rejected() -> None:
    with pytest.raises(InvalidPath) as exc:
        normalize_path("")
    assert exc.value.reason == "path_invalid_length"


def test_above_1024_chars_rejected() -> None:
    with pytest.raises(InvalidPath) as exc:
        normalize_path("a" * 1025)
    assert exc.value.reason == "path_invalid_length"


def test_double_dot_inside_filename_accepted() -> None:
    # "foo/..bar" : "..bar" est un nom de fichier valide, pas un segment ..
    assert normalize_path("foo/..bar") == "foo/..bar"


def test_double_dot_at_segment_boundary_rejected() -> None:
    with pytest.raises(InvalidPath):
        normalize_path("a/../b")
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
uv run pytest tests/unit/services/test_push_path_normalize.py -v
```

Expected: `ModuleNotFoundError: No module named 'rag.services.push'`.

- [ ] **Step 3: Créer `services/push.py` avec `normalize_path`**

```python
# backend/src/rag/services/push.py
from __future__ import annotations

import re

from rag.api.errors import InvalidPath

_PATH_MAX_LEN = 1024
_BAD_SEGMENT = re.compile(r"(^|/)\.\.(/|$)")


def normalize_path(raw: str) -> str:
    """Normalise et valide un path POSIX relatif.

    - remplace `\\` par `/`
    - rejette : NUL byte, leading `/`, segments `..`, vide, > 1024 chars
    """
    if "\x00" in raw:
        raise InvalidPath("path_contains_nul")
    p = raw.replace("\\", "/")
    if p.startswith("/"):
        raise InvalidPath("path_must_be_relative")
    if _BAD_SEGMENT.search(p):
        raise InvalidPath("path_traversal_forbidden")
    if not p or len(p) > _PATH_MAX_LEN:
        raise InvalidPath("path_invalid_length")
    return p
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
uv run pytest tests/unit/services/test_push_path_normalize.py -v
```

Expected: `11 passed`.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/rag/services/push.py backend/tests/unit/services/test_push_path_normalize.py
git commit -m "feat(M4b): normalize_path POSIX relative strict"
```

---

## Task 6: `push_document` service (orchestration)

**Files:**
- Modify: `backend/src/rag/services/push.py`
- Create: `backend/tests/unit/services/test_push_service.py`

- [ ] **Step 1: Écrire les tests d'orchestration (mocks)**

```python
# backend/tests/unit/services/test_push_service.py
from __future__ import annotations

from hashlib import sha256
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.schemas.workspace import (
    PushIndexedResponse,
    PushRequest,
    PushSkippedResponse,
)
from rag.services.push import push_document


class _FakeIndexer:
    def __init__(self, returns_chunks: int = 3) -> None:
        self.returns_chunks = returns_chunks
        self.calls: list[dict[str, Any]] = []

    async def index_file(self, **kw: Any) -> int:
        self.calls.append(kw)
        return self.returns_chunks

    async def delete_file(self, **kw: Any) -> None:
        raise AssertionError("not expected")


def _hash(content: str) -> str:
    return "sha256:" + sha256(content.encode("utf-8")).hexdigest()


@pytest.mark.asyncio
async def test_push_indexes_when_hash_differs() -> None:
    indexer = _FakeIndexer(returns_chunks=4)
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=None)  # rien indexé encore

    ws = uuid4()
    payload = PushRequest(path="docs/foo.md", content="hello world")
    resp = await push_document(
        payload=payload,
        workspace_id=ws,
        indexer_used="openai/text-embedding-3-small",
        config_pool=pool,
        indexer=indexer,
    )

    assert isinstance(resp, PushIndexedResponse)
    assert resp.path == "docs/foo.md"
    assert resp.chunks == 4
    assert resp.hash == _hash("hello world")
    assert len(indexer.calls) == 1
    assert indexer.calls[0]["workspace_id"] == ws
    assert indexer.calls[0]["path"] == "docs/foo.md"
    assert indexer.calls[0]["content_hash"] == _hash("hello world")
    assert indexer.calls[0]["indexer_used"] == "openai/text-embedding-3-small"


@pytest.mark.asyncio
async def test_push_skips_when_hash_identical() -> None:
    content = "stable content"
    indexer = _FakeIndexer()
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=_hash(content))

    payload = PushRequest(path="x.md", content=content)
    resp = await push_document(
        payload=payload,
        workspace_id=uuid4(),
        indexer_used="openai/m",
        config_pool=pool,
        indexer=indexer,
    )

    assert isinstance(resp, PushSkippedResponse)
    assert resp.path == "x.md"
    assert resp.reason == "content_unchanged"
    assert indexer.calls == []  # pas d'appel embed


@pytest.mark.asyncio
async def test_push_normalizes_path_before_indexing() -> None:
    indexer = _FakeIndexer(returns_chunks=1)
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=None)

    payload = PushRequest(path="docs\\sub\\foo.md", content="x")
    resp = await push_document(
        payload=payload,
        workspace_id=uuid4(),
        indexer_used="openai/m",
        config_pool=pool,
        indexer=indexer,
    )

    assert resp.path == "docs/sub/foo.md"
    assert indexer.calls[0]["path"] == "docs/sub/foo.md"


@pytest.mark.asyncio
async def test_push_raises_invalid_path_for_traversal() -> None:
    from rag.api.errors import InvalidPath

    indexer = _FakeIndexer()
    pool = MagicMock()
    pool.fetchval = AsyncMock()

    payload = PushRequest(path="foo/../bar", content="x")
    with pytest.raises(InvalidPath):
        await push_document(
            payload=payload,
            workspace_id=uuid4(),
            indexer_used="openai/m",
            config_pool=pool,
            indexer=indexer,
        )
    pool.fetchval.assert_not_called()


@pytest.mark.asyncio
async def test_push_zero_chunks_still_returns_indexed_response() -> None:
    indexer = _FakeIndexer(returns_chunks=0)
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=None)

    payload = PushRequest(path="empty.md", content=" ")
    resp = await push_document(
        payload=payload,
        workspace_id=uuid4(),
        indexer_used="openai/m",
        config_pool=pool,
        indexer=indexer,
    )
    assert isinstance(resp, PushIndexedResponse)
    assert resp.chunks == 0
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
uv run pytest tests/unit/services/test_push_service.py -v
```

Expected: `ImportError: cannot import name 'push_document' from 'rag.services.push'`.

- [ ] **Step 3: Ajouter `push_document` à `services/push.py`**

Append au fichier `backend/src/rag/services/push.py` :

```python
from hashlib import sha256
from uuid import UUID

import asyncpg
import structlog

from rag.indexer.protocol import IndexerProtocol
from rag.schemas.workspace import (
    PushIndexedResponse,
    PushRequest,
    PushResponse,
    PushSkippedResponse,
)

log = structlog.get_logger(__name__)


async def push_document(
    *,
    payload: PushRequest,
    workspace_id: UUID,
    indexer_used: str,
    config_pool: asyncpg.Pool,
    indexer: IndexerProtocol,
) -> PushResponse:
    """Orchestre un push synchrone : normalize → dedup → index.

    Pré-déduplication sur `indexed_documents.content_hash` : évite
    l'appel embedding si le content est identique au dernier indexé.
    Sinon délègue à `indexer.index_file(...)` qui fait
    chunk + embed + upsert pgvector + UPDATE indexed_documents.
    """
    norm_path = normalize_path(payload.path)
    content_hash = "sha256:" + sha256(payload.content.encode("utf-8")).hexdigest()

    existing = await config_pool.fetchval(
        "SELECT content_hash FROM indexed_documents WHERE workspace_id = $1 AND path = $2",
        workspace_id,
        norm_path,
    )
    if existing == content_hash:
        log.info(
            "push.skipped",
            workspace_id=str(workspace_id),
            path=norm_path,
            reason="content_unchanged",
        )
        return PushSkippedResponse(path=norm_path)

    chunks = await indexer.index_file(
        workspace_id=workspace_id,
        path=norm_path,
        content=payload.content,
        content_hash=content_hash,
        indexer_used=indexer_used,
    )
    log.info(
        "push.indexed",
        workspace_id=str(workspace_id),
        path=norm_path,
        chunks=chunks,
        hash=content_hash,
    )
    return PushIndexedResponse(path=norm_path, chunks=chunks, hash=content_hash)
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
uv run pytest tests/unit/services/test_push_service.py -v
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/rag/services/push.py backend/tests/unit/services/test_push_service.py
git commit -m "feat(M4b): push_document orchestration dedup+index"
```

---

## Task 7: Router `build_workspace_router`

**Files:**
- Create: `backend/src/rag/api/workspace.py`
- Modify: `backend/src/rag/main.py`

Note : ce task introduit le router et le wire dans `main.py` simultanément, parce qu'un router non monté n'est pas testable end-to-end ; les tests integration arrivent en Task 9+ et exigent un endpoint vivant.

- [ ] **Step 1: Écrire le router sans test isolé**

(Pas de test unitaire — le router est trivial et sera couvert intégralement par les tests integration des tasks suivantes.)

```python
# backend/src/rag/api/workspace.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from rag.auth.workspace_auth import AuthContext, require_workspace_apikey
from rag.schemas.workspace import PushRequest, PushResponse
from rag.services.push import push_document


def build_workspace_router() -> APIRouter:
    """Router des endpoints workspace authentifiés par api_key.

    Pour le moment : un seul endpoint, `POST /workspaces/{name}/index` (M4b).
    L'auth est appliquée endpoint par endpoint (pas globalement) : M4c
    (recherche MCP) utilisera un schéma d'auth différent.
    """
    router = APIRouter(tags=["workspace"])

    @router.post("/workspaces/{name}/index", response_model=PushResponse)
    async def push_index(
        name: str,
        payload: PushRequest,
        request: Request,
        auth: AuthContext = Depends(require_workspace_apikey),
    ) -> PushResponse:
        return await push_document(
            payload=payload,
            workspace_id=auth.workspace_id,
            indexer_used=auth.indexer_used,
            config_pool=request.app.state.pools.config_pool,
            indexer=request.app.state.indexer,
        )

    return router
```

- [ ] **Step 2: Modifier `main.py` pour exposer cache + indexer + router**

Patch dans `backend/src/rag/main.py` :

a) Ajouter en haut du fichier (imports) :
```python
from rag.api.workspace import build_workspace_router
from rag.auth.workspace_auth import ApiKeyCache
```

b) Dans le `lifespan`, après la création de `RealIndexer` et avant `SyncWorker(...)`, créer une variable locale et exposer :
```python
        indexer = RealIndexer(
            config_pool=registry.config_pool,
            pool_registry=registry,
            secret_resolver=app.state.resolver,
        )
        app.state.indexer = indexer
        app.state.apikey_cache = ApiKeyCache(max_size=256, ttl_seconds=300)

        sync_worker = SyncWorker(
            config_pool=registry.config_pool,
            storage=RepoStorage(root=settings.sync_repos_root),
            indexer=indexer,
            resolver=app.state.resolver,
            poll_interval_seconds=settings.sync_worker_poll_interval_seconds,
            default_sync_interval_seconds=settings.sync_default_interval_seconds,
        )
```

c) En fin de fonction, ajouter le router :
```python
    app.include_router(build_workspace_router())
```
(juste après `app.include_router(build_admin_router())`)

- [ ] **Step 3: Smoke local — l'app boote**

```powershell
uv run pytest tests/api/test_main.py tests/api/test_admin_wireup.py tests/api/test_sync_wireup.py -v
```

Expected: tous les tests existants passent (pas de régression).

- [ ] **Step 4: Commit**

```powershell
git add backend/src/rag/api/workspace.py backend/src/rag/main.py
git commit -m "feat(M4b): router workspace + wiring main.py (cache + indexer)"
```

---

## Task 8: Cache invalidation sur rotate-apikey

**Files:**
- Modify: `backend/src/rag/services/workspaces.py`
- Modify: `backend/src/rag/api/admin.py`
- Create: `backend/tests/unit/services/test_rotate_invalidates_cache.py`

- [ ] **Step 1: Test : `rotate_apikey` invalide le cache**

```python
# backend/tests/unit/services/test_rotate_invalidates_cache.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.auth.workspace_auth import ApiKeyCache, _CacheEntry
from rag.services.workspaces import rotate_apikey


@pytest.mark.asyncio
async def test_rotate_apikey_calls_invalidate_on_cache(monkeypatch) -> None:
    import time
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    cache.put("ws_x", "old-key", _CacheEntry(
        workspace_id=uuid4(),
        indexer_used="openai/m",
        inserted_at=time.monotonic(),
    ))

    pool = MagicMock()
    # rotate_apikey appelle execute / fetchval ; on simule un succès.
    pool.execute = AsyncMock()
    pool.fetchval = AsyncMock(return_value=1)  # rowcount UPDATE > 0

    # Selon l'impl actuelle, rotate_apikey peut faire fetchrow pour vérifier
    # l'existence. On stub large pour ne pas dépendre du détail :
    pool.fetchrow = AsyncMock(return_value={"id": uuid4()})
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=pool)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    await rotate_apikey(name="ws_x", config_pool=pool, apikey_cache=cache)

    assert cache.get("ws_x", "old-key") is None


@pytest.mark.asyncio
async def test_rotate_apikey_works_without_cache_kwarg() -> None:
    # Rétro-compat : appelable sans `apikey_cache=` (None par défaut).
    pool = MagicMock()
    pool.execute = AsyncMock()
    pool.fetchval = AsyncMock(return_value=1)
    pool.fetchrow = AsyncMock(return_value={"id": uuid4()})
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=pool)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    # Ne doit pas lever
    await rotate_apikey(name="ws_x", config_pool=pool)
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
uv run pytest tests/unit/services/test_rotate_invalidates_cache.py -v
```

Expected: `TypeError: rotate_apikey() got an unexpected keyword argument 'apikey_cache'` (parce que la signature actuelle n'a pas ce param).

- [ ] **Step 3: Modifier `rotate_apikey` pour accepter le cache**

Dans `backend/src/rag/services/workspaces.py`, trouver la fonction `rotate_apikey` et :
- ajouter le param keyword-only `apikey_cache: ApiKeyCache | None = None`
- à la fin de la fonction (après le UPDATE qui a réussi), appeler `apikey_cache.invalidate(name)` si non-None
- ajouter l'import : `from rag.auth.workspace_auth import ApiKeyCache`

Signature attendue :
```python
async def rotate_apikey(
    *,
    name: str,
    config_pool: asyncpg.Pool,
    apikey_cache: ApiKeyCache | None = None,
) -> str:
    # ... corps existant inchangé ...
    # nouvelle_clé générée, UPDATE workspaces.api_key_hash réussi

    if apikey_cache is not None:
        apikey_cache.invalidate(name)

    return new_key  # variable existante
```

(Le détail exact de l'UPDATE/SELECT est conservé tel quel — la modification est strictement additive en fin de fonction.)

- [ ] **Step 4: Run test to verify it passes**

```powershell
uv run pytest tests/unit/services/test_rotate_invalidates_cache.py -v
```

Expected: `2 passed`.

- [ ] **Step 5: Brancher l'admin router**

Dans `backend/src/rag/api/admin.py`, modifier `rotate_apikey_endpoint` :

```python
    @router.post("/workspaces/{name}/rotate-apikey")
    async def rotate_apikey_endpoint(name: str, request: Request) -> ApiKeyRotateResponse:
        new_key = await rotate_apikey(
            name=name,
            config_pool=_config_pool(request),
            apikey_cache=request.app.state.apikey_cache,
        )
        return ApiKeyRotateResponse(api_key=new_key)
```

- [ ] **Step 6: Vérifier que les tests admin existants passent toujours**

```powershell
uv run pytest tests/api/test_admin_workspaces.py -v
```

Expected: tous OK (rétro-compat parce que le param est keyword-only optionnel).

- [ ] **Step 7: Commit**

```powershell
git add backend/src/rag/services/workspaces.py backend/src/rag/api/admin.py backend/tests/unit/services/test_rotate_invalidates_cache.py
git commit -m "feat(M4b): invalidation cache apikey sur rotate-apikey"
```

---

## Task 9: Tests integration — auth workspace happy path

**Files:**
- Create: `backend/tests/api/test_workspace_push_auth.py`

- [ ] **Step 1: Écrire les tests integration auth**

```python
# backend/tests/api/test_workspace_push_auth.py
from __future__ import annotations

from fastapi.testclient import TestClient


def _make_ws(client: TestClient, admin_headers: dict[str, str], name: str) -> str:
    """Crée un workspace et retourne l'api_key clair."""
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


def _stub_indexer(client: TestClient) -> object:
    """Remplace `app.state.indexer` par un fake qui retourne chunks=2."""
    class _Fake:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def index_file(self, **kw):  # type: ignore[no-untyped-def]
            self.calls.append(kw)
            return 2

        async def delete_file(self, **kw):  # type: ignore[no-untyped-def]
            raise AssertionError("delete_file not expected here")

    fake = _Fake()
    client.app.state.indexer = fake  # type: ignore[attr-defined]
    return fake


def test_push_returns_404_for_unknown_workspace(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _stub_indexer(admin_client)
    r = admin_client.post(
        "/workspaces/ghost/index",
        headers={"Authorization": "Bearer some-key"},
        json={"path": "x.md", "content": "y"},
    )
    assert r.status_code == 404
    assert r.json()["error"] == "workspace_not_found"


def test_push_returns_401_without_authorization(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_noauth")
    _stub_indexer(admin_client)
    r = admin_client.post(
        "/workspaces/ws_noauth/index",
        json={"path": "x.md", "content": "y"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "missing_bearer_token"


def test_push_returns_401_wrong_scheme(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_wrongscheme")
    _stub_indexer(admin_client)
    r = admin_client.post(
        "/workspaces/ws_wrongscheme/index",
        headers={"Authorization": "Basic abc"},
        json={"path": "x.md", "content": "y"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_auth_scheme"


def test_push_returns_401_for_invalid_api_key(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_bad_key")
    _stub_indexer(admin_client)
    r = admin_client.post(
        "/workspaces/ws_bad_key/index",
        headers={"Authorization": "Bearer not-the-real-key"},
        json={"path": "x.md", "content": "y"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


def test_push_returns_200_with_valid_api_key(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_ok")
    fake = _stub_indexer(admin_client)
    r = admin_client.post(
        "/workspaces/ws_ok/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"path": "docs/foo.md", "content": "hello world"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "indexed"
    assert body["path"] == "docs/foo.md"
    assert body["chunks"] == 2
    assert body["hash"].startswith("sha256:")
    assert len(fake.calls) == 1
    assert fake.calls[0]["indexer_used"] == "openai/text-embedding-3-small"


def test_push_cross_workspace_key_returns_401(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key_a = _make_ws(admin_client, admin_headers, "ws_a")
    _make_ws(admin_client, admin_headers, "ws_b")
    _stub_indexer(admin_client)
    r = admin_client.post(
        "/workspaces/ws_b/index",
        headers={"Authorization": f"Bearer {key_a}"},
        json={"path": "x.md", "content": "y"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


def test_rotate_apikey_invalidates_cache(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key_v1 = _make_ws(admin_client, admin_headers, "ws_rot")
    _stub_indexer(admin_client)

    # 1er push : succès avec v1 → met en cache
    r = admin_client.post(
        "/workspaces/ws_rot/index",
        headers={"Authorization": f"Bearer {api_key_v1}"},
        json={"path": "a.md", "content": "x"},
    )
    assert r.status_code == 200

    # rotate la clé
    r2 = admin_client.post("/workspaces/ws_rot/rotate-apikey", headers=admin_headers)
    assert r2.status_code == 200

    # push avec l'ancienne clé : doit échouer 401 (cache invalidé + nouveau hash en DB)
    r3 = admin_client.post(
        "/workspaces/ws_rot/index",
        headers={"Authorization": f"Bearer {api_key_v1}"},
        json={"path": "a.md", "content": "y"},
    )
    assert r3.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
uv run pytest tests/api/test_workspace_push_auth.py -v
```

Expected: la plupart passent dès maintenant — sinon des incohérences de wiring à corriger jusqu'à 7/7 verts.

- [ ] **Step 3: Si échec → diagnostic puis fix**

Lecture des erreurs : si `app.state.indexer` n'existe pas → la modif Task 7 est incomplète. Si 401 où on attendait 200 → vérifier que l'api_key est bien stockée hashée. Itérer jusqu'à 7/7.

- [ ] **Step 4: Run final pour confirmer 7/7**

```powershell
uv run pytest tests/api/test_workspace_push_auth.py -v
```

Expected: `7 passed`.

- [ ] **Step 5: Commit**

```powershell
git add backend/tests/api/test_workspace_push_auth.py
git commit -m "test(M4b): integration auth workspace push (404/401/200/cache/rotate)"
```

---

## Task 10: Tests integration — dedup & re-index

**Files:**
- Create: `backend/tests/api/test_workspace_push_dedup.py`

- [ ] **Step 1: Écrire les tests dedup**

```python
# backend/tests/api/test_workspace_push_dedup.py
from __future__ import annotations

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


def _stub_indexer(client: TestClient):  # type: ignore[no-untyped-def]
    class _Fake:
        def __init__(self) -> None:
            self.indexed: dict[tuple, str] = {}

        async def index_file(self, **kw):  # type: ignore[no-untyped-def]
            self.indexed[(kw["workspace_id"], kw["path"])] = kw["content_hash"]
            return 1

        async def delete_file(self, **kw):  # type: ignore[no-untyped-def]
            self.indexed.pop((kw["workspace_id"], kw["path"]), None)

    fake = _Fake()
    client.app.state.indexer = fake  # type: ignore[attr-defined]
    return fake


def test_second_push_same_content_returns_skipped(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    """Le fake indexer écrit le hash dans `indexed_documents` ?

    Non — le fake ne touche pas la table. On doit donc faire le insert
    manuellement via une fixture, OU utiliser un fake qui simule l'UPDATE.

    Approche choisie : on remplace indexer.index_file pour qu'il insère
    aussi dans indexed_documents (mimique RealIndexer).
    """
    api_key = _make_ws(admin_client, admin_headers, "ws_dedup1")

    # Indexer qui inscrit le hash dans indexed_documents (mimique RealIndexer)
    import asyncio
    import asyncpg

    pool_dsn = pg_container

    class _DedupFake:
        def __init__(self) -> None:
            self.index_calls = 0

        async def index_file(self, **kw):  # type: ignore[no-untyped-def]
            self.index_calls += 1
            conn = await asyncpg.connect(pool_dsn)
            try:
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
                    kw["workspace_id"], kw["path"], kw["content_hash"], kw["indexer_used"],
                )
            finally:
                await conn.close()
            return 1

        async def delete_file(self, **kw):  # type: ignore[no-untyped-def]
            pass

    fake = _DedupFake()
    admin_client.app.state.indexer = fake  # type: ignore[attr-defined]

    headers = {"Authorization": f"Bearer {api_key}"}

    # 1er push
    r1 = admin_client.post(
        "/workspaces/ws_dedup1/index",
        headers=headers,
        json={"path": "doc.md", "content": "stable content"},
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "indexed"

    # 2e push même contenu
    r2 = admin_client.post(
        "/workspaces/ws_dedup1/index",
        headers=headers,
        json={"path": "doc.md", "content": "stable content"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["status"] == "skipped"
    assert body["reason"] == "content_unchanged"
    assert fake.index_calls == 1  # pas de 2e appel à index_file


def test_push_different_content_same_path_reindexes(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_dedup2")

    import asyncpg

    pool_dsn = pg_container

    class _DedupFake:
        def __init__(self) -> None:
            self.calls = 0

        async def index_file(self, **kw):  # type: ignore[no-untyped-def]
            self.calls += 1
            conn = await asyncpg.connect(pool_dsn)
            try:
                await conn.execute(
                    """
                    INSERT INTO indexed_documents
                        (workspace_id, path, content_hash, indexer_used, indexed_at)
                    VALUES ($1, $2, $3, $4, now())
                    ON CONFLICT (workspace_id, path) DO UPDATE
                    SET content_hash=EXCLUDED.content_hash, indexed_at=now()
                    """,
                    kw["workspace_id"], kw["path"], kw["content_hash"], kw["indexer_used"],
                )
            finally:
                await conn.close()
            return 1

        async def delete_file(self, **kw):  # type: ignore[no-untyped-def]
            pass

    fake = _DedupFake()
    admin_client.app.state.indexer = fake  # type: ignore[attr-defined]

    headers = {"Authorization": f"Bearer {api_key}"}

    r1 = admin_client.post(
        "/workspaces/ws_dedup2/index",
        headers=headers,
        json={"path": "doc.md", "content": "v1"},
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "indexed"

    r2 = admin_client.post(
        "/workspaces/ws_dedup2/index",
        headers=headers,
        json={"path": "doc.md", "content": "v2 different"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["status"] == "indexed"
    assert body["hash"] != r1.json()["hash"]
    assert fake.calls == 2
```

- [ ] **Step 2: Run test to verify it passes**

```powershell
uv run pytest tests/api/test_workspace_push_dedup.py -v
```

Expected: `2 passed`. (Pas de "fail first" pour ces tests integration car ils dépendent uniquement de l'API déjà construite aux Tasks 7-8.)

- [ ] **Step 3: Commit**

```powershell
git add backend/tests/api/test_workspace_push_dedup.py
git commit -m "test(M4b): integration dedup + reindex push synchrone"
```

---

## Task 11: Tests integration — codes erreur (422, 413)

**Files:**
- Create: `backend/tests/api/test_workspace_push_errors.py`

- [ ] **Step 1: Écrire les tests d'erreurs**

```python
# backend/tests/api/test_workspace_push_errors.py
from __future__ import annotations

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


def _stub_indexer_noop(client: TestClient) -> None:
    class _Fake:
        async def index_file(self, **kw):  # type: ignore[no-untyped-def]
            return 1

        async def delete_file(self, **kw):  # type: ignore[no-untyped-def]
            pass

    client.app.state.indexer = _Fake()  # type: ignore[attr-defined]


def test_push_returns_422_for_path_traversal(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_e_a")
    _stub_indexer_noop(admin_client)
    r = admin_client.post(
        "/workspaces/ws_e_a/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"path": "foo/../bar", "content": "y"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "invalid_path"
    assert body["reason"] == "path_traversal_forbidden"


def test_push_returns_422_for_absolute_path(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_e_b")
    _stub_indexer_noop(admin_client)
    r = admin_client.post(
        "/workspaces/ws_e_b/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"path": "/etc/passwd", "content": "y"},
    )
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_path"


def test_push_returns_422_for_missing_body_field(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_e_c")
    _stub_indexer_noop(admin_client)
    r = admin_client.post(
        "/workspaces/ws_e_c/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"path": "x.md"},  # content manquant
    )
    assert r.status_code == 422


def test_push_returns_413_for_content_above_5mb(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_e_d")
    _stub_indexer_noop(admin_client)
    # Pydantic validator lève ValueError("content_too_large") → handler
    # custom remap en 413 avec payload ContentTooLarge.
    big = "a" * (5 * 1024 * 1024 + 1)
    r = admin_client.post(
        "/workspaces/ws_e_d/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"path": "big.md", "content": big},
    )
    assert r.status_code == 413
    body = r.json()
    assert body["error"] == "content_too_large"
    assert body["limit_bytes"] == 5 * 1024 * 1024


def test_push_returns_422_for_other_validation_errors_unchanged(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    """Régression : le handler RequestValidationError ne doit pas hijacker
    les autres erreurs de validation (champ manquant, mauvais type, etc.)."""
    api_key = _make_ws(admin_client, admin_headers, "ws_e_e")
    _stub_indexer_noop(admin_client)
    r = admin_client.post(
        "/workspaces/ws_e_e/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"path": 123, "content": "x"},  # path: int au lieu de str
    )
    assert r.status_code == 422
    body = r.json()
    # Format Pydantic standard : {"detail": [...]}
    assert "detail" in body
```

- [ ] **Step 2: Run test to verify it passes**

```powershell
uv run pytest tests/api/test_workspace_push_errors.py -v
```

Expected: `5 passed`.

- [ ] **Step 3: Commit**

```powershell
git add backend/tests/api/test_workspace_push_errors.py
git commit -m "test(M4b): integration codes erreurs push (422 path / 413 size)"
```

---

## Task 12: Smoke test E2E Ollama (opt-in)

**Files:**
- Create: `backend/tests/smoke/test_push_e2e_ollama.py`

- [ ] **Step 1: Écrire le smoke test E2E**

```python
# backend/tests/smoke/test_push_e2e_ollama.py
from __future__ import annotations

import os

import asyncpg
import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.smoke


@pytest.fixture
def ollama_url() -> str:
    url = os.environ.get("OLLAMA_TEST_URL")
    if not url:
        pytest.skip("OLLAMA_TEST_URL non défini — smoke push Ollama sauté.")
    return url


def test_push_e2e_indexes_embeddings_in_pgvector(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
    ollama_url: str,
) -> None:
    """End-to-end : crée un workspace Ollama, push 1 doc, vérifie pgvector."""
    # 1. Crée le workspace avec provider Ollama (pas d'api_key_ref nécessaire).
    r = admin_client.post(
        "/workspaces",
        headers=admin_headers,
        json={
            "name": "ws_smoke_ollama",
            "indexer": {
                "provider": "ollama",
                "model": "nomic-embed-text",
                "base_url": ollama_url,
            },
        },
    )
    assert r.status_code == 201, r.text
    api_key = r.json()["api_key"]

    # 2. Push un doc.
    r2 = admin_client.post(
        "/workspaces/ws_smoke_ollama/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "path": "smoke/hello.md",
            "content": "Hello vector world. This is a smoke test for push.",
        },
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["status"] == "indexed"
    assert body["chunks"] >= 1

    # 3. Vérifie pgvector : embeddings table contient au moins 1 ligne.
    import asyncio

    async def _check() -> int:
        admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
        admin = await asyncpg.connect(admin_dsn)
        try:
            row = await admin.fetchrow(
                "SELECT datname FROM pg_database WHERE datname = 'rag_ws_smoke_ollama'"
            )
            assert row is not None, "workspace DB missing"
        finally:
            await admin.close()

        ws_dsn = pg_container.rsplit("/", 1)[0] + "/rag_ws_smoke_ollama"
        conn = await asyncpg.connect(ws_dsn)
        try:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM embeddings WHERE path = $1",
                "smoke/hello.md",
            )
            return int(count or 0)
        finally:
            await conn.close()

    chunks_in_db = asyncio.get_event_loop().run_until_complete(_check())
    assert chunks_in_db >= 1
```

- [ ] **Step 2: Vérifier que le smoke est skippé par défaut**

```powershell
uv run pytest tests/smoke/test_push_e2e_ollama.py -v
```

Expected: `1 deselected` (à cause de `addopts = "-m 'not smoke'"` dans `pyproject.toml`).

- [ ] **Step 3: Si Ollama dispo, faire tourner le smoke**

```powershell
$env:OLLAMA_TEST_URL = "http://192.168.10.80:11434"
uv run pytest tests/smoke/test_push_e2e_ollama.py -m smoke -v
```

Expected (si Ollama dispo): `1 passed`. Sinon `1 skipped`.

- [ ] **Step 4: Commit**

```powershell
git add backend/tests/smoke/test_push_e2e_ollama.py
git commit -m "test(M4b): smoke E2E push Ollama avec verif pgvector"
```

---

## Task 13: Quality gate — ruff, mypy, coverage globale

**Files:**
- No code changes (sauf corrections si gates échouent)

- [ ] **Step 1: ruff check + format**

```powershell
uv run ruff check src tests
uv run ruff format --check src tests
```

Expected: `All checks passed!` et `N files already formatted`.

Si erreurs : corriger avec `uv run ruff check --fix src tests` puis `uv run ruff format src tests`.

- [ ] **Step 2: mypy strict**

```powershell
uv run mypy src/rag
```

Expected: `Success: no issues found in N source files`.

Si erreurs : corriger les annotations manquantes / mauvais types. Pour les attributs `app.state.*` dynamiques, le pattern existant utilise `# type: ignore[arg-type]` ou `# type: ignore[attr-defined]` localement.

- [ ] **Step 3: pytest complet avec couverture**

```powershell
uv run pytest --cov=src/rag --cov-report=term-missing -q
```

Expected:
- Tous les tests verts (non-smoke).
- Couverture globale ≥ 95%.
- Modules M4b ≥ 95% chacun (`auth/workspace_auth.py`, `services/push.py`, `api/workspace.py`, `schemas/workspace.py`).

Si couverture en-dessous : identifier les branches non couvertes (`term-missing` affiche les lignes) et ajouter des tests unitaires ciblés.

- [ ] **Step 4: Commit si corrections appliquées (sinon skip)**

```powershell
git add -u
git commit -m "chore(M4b): corrections quality gate (lint/mypy/coverage)"
```

---

## Task 14: Smoke deploy LXC 303 + tag m4b-done

**Files:**
- No code changes

- [ ] **Step 1: Push la branche dev**

```powershell
git push origin dev
```

- [ ] **Step 2: Déployer sur LXC 303 via dev-deploy.sh**

```powershell
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && ./dev-deploy.sh'"
```

Attendre que le script affiche le rebuild + restart du conteneur backend.

Expected (extraits) :
- Pull git ok
- Build image backend ok
- Compose up ok
- Healthcheck backend ok

- [ ] **Step 3: Smoke API depuis le Windows dev**

```powershell
# /health
curl http://192.168.10.184:8000/health

# /version : git SHA = celui de la branche
curl http://192.168.10.184:8000/version
```

Expected: `/health` retourne `{"status":"ok"}`, `/version` retourne le SHA du dernier commit dev.

- [ ] **Step 4: Smoke push réel contre un workspace test**

```powershell
# Récupérer la master key depuis l'env du LXC 303 (ou la doc)
# Créer un workspace de test :
$env:MASTER_KEY = "<RAG_MASTER_KEY du LXC 303>"

$resp = Invoke-RestMethod -Method Post -Uri http://192.168.10.184:8000/workspaces `
    -Headers @{ Authorization = "Bearer $env:MASTER_KEY"; "Content-Type" = "application/json" } `
    -Body '{"name":"smoke_m4b","indexer":{"provider":"ollama","model":"nomic-embed-text","base_url":"http://192.168.10.80:11434"}}'

$apiKey = $resp.api_key

# Push un doc :
$pushBody = @{ path = "smoke/doc.md"; content = "Hello from M4b smoke." } | ConvertTo-Json
$pushResp = Invoke-RestMethod -Method Post -Uri http://192.168.10.184:8000/workspaces/smoke_m4b/index `
    -Headers @{ Authorization = "Bearer $apiKey"; "Content-Type" = "application/json" } `
    -Body $pushBody

$pushResp | ConvertTo-Json
```

Expected: réponse `{"path": "smoke/doc.md", "status": "indexed", "chunks": N, "hash": "sha256:..."}`.

- [ ] **Step 5: Vérifier les logs Loki**

Ouvrir Grafana → Explore → Loki → query `{container_name="rag-backend"} |= "push.indexed"`.

Expected : un événement JSON `push.indexed workspace_id=... path=smoke/doc.md chunks=N hash=sha256:...`.

- [ ] **Step 6: Nettoyer le workspace de smoke**

```powershell
Invoke-RestMethod -Method Delete -Uri http://192.168.10.184:8000/workspaces/smoke_m4b `
    -Headers @{ Authorization = "Bearer $env:MASTER_KEY" }
```

- [ ] **Step 7: Tag m4b-done et push**

```powershell
git tag -a m4b-done -m "M4b: API push synchrone /workspaces/{name}/index"
git push origin m4b-done
```

Expected: `* [new tag] m4b-done -> m4b-done`.

---

## Récapitulatif de couverture (cible)

| Module | Cible |
|---|---|
| `backend/src/rag/auth/workspace_auth.py` | 100% |
| `backend/src/rag/services/push.py` | ≥ 95% |
| `backend/src/rag/api/workspace.py` | 100% (via integration) |
| `backend/src/rag/schemas/workspace.py` | 100% |
| `backend/src/rag/api/errors.py` (nouveaux ajouts) | 100% |
| `backend/src/rag/services/workspaces.py::rotate_apikey` (modif) | 100% des nouvelles lignes |
| **Couverture globale projet** | ≥ 95% (maintenir le niveau M4a) |

## Hors scope (rappel — pas dans ce plan)

- DELETE push (`DELETE /workspaces/{name}/index/{path}`)
- Batch push (`POST /workspaces/{name}/index/batch`)
- Rate-limiting applicatif côté RAG
- Granularité scopes api_key (read-only, write-only)
- Cache distribué multi-instance (Redis pub/sub)
- Trace push dans `index_jobs` ou table dédiée
- Configuration timeout Caddy (mention infra à faire dans la PR, pas du code)
