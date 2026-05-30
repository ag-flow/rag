# Provider API Keys — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un onglet "Apikeys" dans la page de détail d'un coffre Harpocrate permettant de pré-stocker des clés API de providers d'embedding/reranking (openai, voyage, mistral…) directement dans Harpocrate.

**Architecture:** Nouvelle table `provider_api_keys` (métadonnées en DB + valeur dans Harpocrate au path `/<vault-name>/<provider>/<key_id>`). Service fonctionnel (`services/provider_api_keys.py`) qui délègue l'accès Harpocrate via le `HarpocrateVaultsService` existant. Router FastAPI monté sous `/api/admin/harpocrate-vaults/{vault_id}/provider-keys`. Frontend React : onglet + 2 dialogs suivant le pattern `ReplaceApiKeyDialog`.

**Tech Stack:** Python 3.12 + FastAPI + asyncpg + `asyncio.to_thread` pour les appels SDK Harpocrate (sync) + React 18 + TanStack Query + shadcn/ui + i18next.

---

## Fichiers créés / modifiés

### Backend — nouveaux
- `backend/migrations/024_provider_api_keys.sql`
- `backend/src/rag/schemas/provider_api_keys.py`
- `backend/src/rag/services/provider_api_keys.py`
- `backend/src/rag/api/admin_provider_keys.py`
- `backend/tests/integration/test_migration_024.py`
- `backend/tests/integration/test_services_provider_api_keys.py`

### Backend — modifiés
- `backend/src/rag/main.py` — mount du nouveau router

### Frontend — nouveaux
- `frontend/src/pages/harpocrate/VaultApikeysTab.tsx`
- `frontend/src/pages/harpocrate/AddProviderKeyDialog.tsx`
- `frontend/src/pages/harpocrate/ReplaceProviderKeyDialog.tsx`

### Frontend — modifiés
- `frontend/src/lib/harpocrate-vaults.types.ts` — types ProviderApiKey*
- `frontend/src/lib/harpocrate-vaults.ts` — 4 méthodes API
- `frontend/src/hooks/useHarpocrateVaults.ts` — 4 hooks
- `frontend/src/pages/harpocrate/VaultDetailPanel.tsx` — 4ème onglet
- `frontend/src/i18n/fr/harpocrate.json` — clés `apikeys.*` + `tabs.apikeys`
- `frontend/src/i18n/en/harpocrate.json` — idem en anglais

---

## Task 1 : Migration 024 + test

**Files:**
- Create: `backend/migrations/024_provider_api_keys.sql`
- Create: `backend/tests/integration/test_migration_024.py`

- [ ] **Écrire le SQL de migration**

```sql
-- Migration 024 — clés API provider stockées dans Harpocrate

CREATE TABLE provider_api_keys (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_id      TEXT NOT NULL,
    label       TEXT NOT NULL,
    provider    TEXT NOT NULL,
    vault_id    UUID NOT NULL REFERENCES harpocrate_vaults(id) ON DELETE RESTRICT,
    harpo_path  TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (vault_id, provider, key_id)
);
```

- [ ] **Écrire le test de migration**

```python
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def test_migration_024_table_and_constraints(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        # Insérer un coffre minimal pour satisfaire la FK
        vault_id = await conn.fetchval(
            "INSERT INTO harpocrate_vaults "
            "(id, name, label, base_url, api_key_id, api_key_encrypted, is_default) "
            "VALUES (gen_random_uuid(), 'v024', 'V024', 'https://h.io', 'kid', 'enc', false) "
            "RETURNING id"
        )

        # Insertion normale
        pk_id = await conn.fetchval(
            "INSERT INTO provider_api_keys (key_id, label, provider, vault_id, harpo_path) "
            "VALUES ('my-key', 'My Key', 'openai', $1, '/v024/openai/my-key') "
            "RETURNING id",
            vault_id,
        )
        assert pk_id is not None

        # Contrainte UNIQUE (vault_id, provider, key_id)
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO provider_api_keys (key_id, label, provider, vault_id, harpo_path) "
                "VALUES ('my-key', 'Dup', 'openai', $1, '/v024/openai/my-key')",
                vault_id,
            )

        # ON DELETE RESTRICT : le coffre ne peut pas être supprimé
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await conn.execute(
                "DELETE FROM harpocrate_vaults WHERE id = $1", vault_id
            )
```

- [ ] **Lancer le test**

```bash
cd backend
uv run pytest tests/integration/test_migration_024.py -v
```

Expected: PASS.

- [ ] **Commit**

```bash
git add backend/migrations/024_provider_api_keys.sql backend/tests/integration/test_migration_024.py
git commit -m "feat(db): migration 024 — table provider_api_keys"
```

---

## Task 2 : Schemas Pydantic

**Files:**
- Create: `backend/src/rag/schemas/provider_api_keys.py`

- [ ] **Créer le fichier**

```python
from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_KEY_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


class ProviderApiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=4096)

    @field_validator("key_id")
    @classmethod
    def _v_key_id(cls, v: str) -> str:
        if not _KEY_ID_RE.match(v):
            raise ValueError("key_id doit matcher ^[a-zA-Z0-9_-]+$")
        return v


class ProviderApiKeyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=128)
    value: str | None = Field(default=None, min_length=1, max_length=4096)


class ProviderApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key_id: str
    label: str
    provider: str
    harpo_path: str
    created_at: datetime
```

- [ ] **Lint + mypy**

```bash
cd backend
uv run ruff check src/rag/schemas/provider_api_keys.py
uv run mypy src/rag/schemas/provider_api_keys.py
```

Expected: no errors.

- [ ] **Commit**

```bash
git add backend/src/rag/schemas/provider_api_keys.py
git commit -m "feat(schemas): DTOs ProviderApiKey"
```

---

## Task 3 : Service + tests d'intégration

**Files:**
- Create: `backend/src/rag/services/provider_api_keys.py`
- Create: `backend/tests/integration/test_services_provider_api_keys.py`

- [ ] **Écrire les tests d'intégration (rouge)**

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.schemas.provider_api_keys import ProviderApiKeyCreate, ProviderApiKeyUpdate
from rag.services.provider_api_keys import (
    create_provider_key,
    delete_provider_key,
    list_provider_keys,
    update_provider_key,
)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.fixture
async def pool(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
    return session_pool


async def _seed_vault(pool: asyncpg.Pool, name: str = "v1") -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO harpocrate_vaults "
            "(id, name, label, base_url, api_key_id, api_key_encrypted, is_default) "
            "VALUES (gen_random_uuid(), $1, $1, 'https://h.io', 'kid', 'enc', false) "
            "RETURNING id, name",
            name,
        )
        return {"id": str(row["id"]), "name": row["name"], "base_url": "https://h.io"}


def _mock_vault_svc(vault: dict, api_key: str = "tok") -> MagicMock:
    svc = MagicMock()
    svc.reveal_api_key = MagicMock(return_value=api_key)
    return svc


async def test_create_and_list(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool)
    svc = _mock_vault_svc(vault)

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        async with pool.acquire() as conn:
            created = await create_provider_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=ProviderApiKeyCreate(
                    key_id="prod-openai",
                    label="OpenAI Prod",
                    provider="openai",
                    value="sk-test",
                ),
            )

    assert created.key_id == "prod-openai"
    assert created.harpo_path == f"/v1/openai/prod-openai"
    mock_client.set_secret.assert_called_once_with("/v1/openai/prod-openai", "sk-test")

    async with pool.acquire() as conn:
        keys = await list_provider_keys(conn, vault_id=vault["id"])
    assert len(keys) == 1
    assert keys[0].key_id == "prod-openai"


async def test_create_duplicate_409(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v2")
    svc = _mock_vault_svc(vault)

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            await create_provider_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=ProviderApiKeyCreate(
                    key_id="dup", label="Dup", provider="openai", value="v"
                ),
            )

    from rag.services.provider_api_keys import DuplicateProviderKeyError

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient"):
        with pytest.raises(DuplicateProviderKeyError):
            async with pool.acquire() as conn:
                await create_provider_key(
                    conn,
                    vault=vault,
                    vault_svc=svc,
                    req=ProviderApiKeyCreate(
                        key_id="dup", label="Dup2", provider="openai", value="v2"
                    ),
                )


async def test_update_label(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v3")
    svc = _mock_vault_svc(vault)

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await create_provider_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=ProviderApiKeyCreate(
                    key_id="k1", label="Old Label", provider="voyage", value="v"
                ),
            )

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            updated = await update_provider_key(
                conn,
                key_id=str(created.id),
                vault=vault,
                vault_svc=svc,
                req=ProviderApiKeyUpdate(label="New Label"),
            )

    assert updated is not None
    assert updated.label == "New Label"


async def test_delete_unreferenced(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v4")
    svc = _mock_vault_svc(vault)

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        async with pool.acquire() as conn:
            created = await create_provider_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=ProviderApiKeyCreate(
                    key_id="del-me", label="L", provider="openai", value="v"
                ),
            )

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        async with pool.acquire() as conn:
            deleted = await delete_provider_key(
                conn,
                key_id=str(created.id),
                vault=vault,
                vault_svc=svc,
            )

    assert deleted is True
    mock_client.delete_secret.assert_called_once()

    async with pool.acquire() as conn:
        keys = await list_provider_keys(conn, vault_id=vault["id"])
    assert keys == []
```

- [ ] **Lancer les tests pour vérifier qu'ils échouent**

```bash
cd backend
uv run pytest tests/integration/test_services_provider_api_keys.py -v
```

Expected: ImportError (module inexistant).

- [ ] **Créer `services/provider_api_keys.py`**

```python
from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from rag.schemas.provider_api_keys import (
    ProviderApiKeyCreate,
    ProviderApiKeyOut,
    ProviderApiKeyUpdate,
)
from rag.secrets.vault import HarpocrateVaultClient

log = structlog.get_logger(__name__)


class DuplicateProviderKeyError(Exception):
    pass


class ProviderKeyNotFoundError(Exception):
    pass


class ProviderKeyReferencedError(Exception):
    pass


def _build_harpo_path(vault_name: str, provider: str, key_id: str) -> str:
    return f"/{vault_name}/{provider}/{key_id}"


async def _get_vault_client(
    conn: asyncpg.Connection,
    vault: dict[str, Any],
    vault_svc: Any,
) -> HarpocrateVaultClient:
    api_key = await vault_svc.reveal_api_key(conn, UUID(vault["id"]))
    if api_key is None:
        raise RuntimeError("Cannot decrypt vault API key — DEK manquant ?")
    return HarpocrateVaultClient(url=vault["base_url"], token=api_key)


async def list_provider_keys(
    conn: asyncpg.Connection,
    *,
    vault_id: str,
) -> list[ProviderApiKeyOut]:
    rows = await conn.fetch(
        "SELECT id, key_id, label, provider, harpo_path, created_at "
        "FROM provider_api_keys WHERE vault_id = $1::uuid "
        "ORDER BY provider, key_id",
        vault_id,
    )
    return [ProviderApiKeyOut.model_validate(dict(r)) for r in rows]


async def create_provider_key(
    conn: asyncpg.Connection,
    *,
    vault: dict[str, Any],
    vault_svc: Any,
    req: ProviderApiKeyCreate,
) -> ProviderApiKeyOut:
    harpo_path = _build_harpo_path(vault["name"], req.provider, req.key_id)

    # Écriture dans Harpocrate (SDK sync → thread)
    client = await _get_vault_client(conn, vault, vault_svc)
    await asyncio.to_thread(client.set_secret, harpo_path, req.value)

    try:
        row = await conn.fetchrow(
            "INSERT INTO provider_api_keys (key_id, label, provider, vault_id, harpo_path) "
            "VALUES ($1, $2, $3, $4::uuid, $5) "
            "RETURNING id, key_id, label, provider, harpo_path, created_at",
            req.key_id,
            req.label,
            req.provider,
            vault["id"],
            harpo_path,
        )
    except asyncpg.UniqueViolationError as exc:
        # Rollback Harpocrate best-effort (idempotent)
        await asyncio.to_thread(client.delete_secret, harpo_path)
        raise DuplicateProviderKeyError(
            f"key_id={req.key_id!r} already exists for provider={req.provider!r}"
        ) from exc

    log.info(
        "provider_key.created",
        vault_id=vault["id"],
        provider=req.provider,
        key_id=req.key_id,
    )
    return ProviderApiKeyOut.model_validate(dict(row))


async def update_provider_key(
    conn: asyncpg.Connection,
    *,
    key_id: str,
    vault: dict[str, Any],
    vault_svc: Any,
    req: ProviderApiKeyUpdate,
) -> ProviderApiKeyOut | None:
    row = await conn.fetchrow(
        "SELECT id, key_id, label, provider, harpo_path, created_at "
        "FROM provider_api_keys WHERE id = $1::uuid AND vault_id = $2::uuid",
        key_id,
        vault["id"],
    )
    if row is None:
        return None

    if req.value is not None:
        client = await _get_vault_client(conn, vault, vault_svc)
        await asyncio.to_thread(client.set_secret, row["harpo_path"], req.value)

    new_label = req.label if req.label is not None else row["label"]
    updated = await conn.fetchrow(
        "UPDATE provider_api_keys SET label = $1 WHERE id = $2::uuid "
        "RETURNING id, key_id, label, provider, harpo_path, created_at",
        new_label,
        key_id,
    )
    log.info("provider_key.updated", id=key_id)
    return ProviderApiKeyOut.model_validate(dict(updated))


async def delete_provider_key(
    conn: asyncpg.Connection,
    *,
    key_id: str,
    vault: dict[str, Any],
    vault_svc: Any,
) -> bool:
    row = await conn.fetchrow(
        "SELECT id, harpo_path FROM provider_api_keys "
        "WHERE id = $1::uuid AND vault_id = $2::uuid",
        key_id,
        vault["id"],
    )
    if row is None:
        return False

    # Vérification de référence : aucun workspace ne doit utiliser ce harpo_path
    ref_count = await conn.fetchval(
        "SELECT count(*) FROM workspaces WHERE api_key_ref LIKE $1",
        f"%{row['harpo_path']}%",
    )
    if int(ref_count or 0) > 0:
        raise ProviderKeyReferencedError(
            f"harpo_path={row['harpo_path']!r} referenced in workspaces"
        )

    # Suppression Harpocrate (best-effort)
    client = await _get_vault_client(conn, vault, vault_svc)
    await asyncio.to_thread(client.delete_secret, row["harpo_path"])

    await conn.execute("DELETE FROM provider_api_keys WHERE id = $1::uuid", key_id)
    log.info("provider_key.deleted", id=key_id, harpo_path=row["harpo_path"])
    return True
```

- [ ] **Lancer les tests**

```bash
cd backend
uv run pytest tests/integration/test_services_provider_api_keys.py -v
```

Expected: 4 tests PASS.

- [ ] **Lint + mypy**

```bash
uv run ruff check src/rag/services/provider_api_keys.py
uv run mypy src/rag/services/provider_api_keys.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/services/provider_api_keys.py backend/tests/integration/test_services_provider_api_keys.py
git commit -m "feat(services): CRUD provider_api_keys avec Harpocrate"
```

---

## Task 4 : Router API + mount

**Files:**
- Create: `backend/src/rag/api/admin_provider_keys.py`
- Modify: `backend/src/rag/main.py`

- [ ] **Créer `api/admin_provider_keys.py`**

```python
from __future__ import annotations

from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.schemas.provider_api_keys import (
    ProviderApiKeyCreate,
    ProviderApiKeyOut,
    ProviderApiKeyUpdate,
)
from rag.services.provider_api_keys import (
    DuplicateProviderKeyError,
    ProviderKeyNotFoundError,
    ProviderKeyReferencedError,
    create_provider_key,
    delete_provider_key,
    list_provider_keys,
    update_provider_key,
)

log = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/admin/harpocrate-vaults/{vault_id}/provider-keys",
    tags=["admin-provider-keys"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


def _pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pools.config_pool  # type: ignore[no-any-return]


def _vault_svc(request: Request) -> object:
    return request.app.state.harpocrate_vaults_service


@router.get("", response_model=list[ProviderApiKeyOut])
async def list_keys(vault_id: UUID, request: Request) -> list[ProviderApiKeyOut]:
    pool = _pool(request)
    async with pool.acquire() as conn:
        return await list_provider_keys(conn, vault_id=str(vault_id))


@router.post("", response_model=ProviderApiKeyOut, status_code=201)
async def create_key(
    vault_id: UUID,
    body: ProviderApiKeyCreate,
    request: Request,
) -> ProviderApiKeyOut:
    pool = _pool(request)
    svc = _vault_svc(request)
    async with pool.acquire() as conn:
        vault = await svc.get_by_id(conn, vault_id)
        if vault is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
        vault_dict = {"id": str(vault.id), "name": vault.name, "base_url": vault.base_url}
        try:
            return await create_provider_key(conn, vault=vault_dict, vault_svc=svc, req=body)
        except DuplicateProviderKeyError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.patch("/{key_id}", response_model=ProviderApiKeyOut)
async def update_key(
    vault_id: UUID,
    key_id: UUID,
    body: ProviderApiKeyUpdate,
    request: Request,
) -> ProviderApiKeyOut:
    pool = _pool(request)
    svc = _vault_svc(request)
    async with pool.acquire() as conn:
        vault = await svc.get_by_id(conn, vault_id)
        if vault is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
        vault_dict = {"id": str(vault.id), "name": vault.name, "base_url": vault.base_url}
        result = await update_provider_key(
            conn, key_id=str(key_id), vault=vault_dict, vault_svc=svc, req=body
        )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "provider key not found")
    return result


@router.delete("/{key_id}", status_code=204)
async def delete_key(
    vault_id: UUID,
    key_id: UUID,
    request: Request,
) -> Response:
    pool = _pool(request)
    svc = _vault_svc(request)
    async with pool.acquire() as conn:
        vault = await svc.get_by_id(conn, vault_id)
        if vault is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
        vault_dict = {"id": str(vault.id), "name": vault.name, "base_url": vault.base_url}
        try:
            deleted = await delete_provider_key(
                conn, key_id=str(key_id), vault=vault_dict, vault_svc=svc
            )
        except ProviderKeyReferencedError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "provider key not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Monter le router dans `main.py`**

Lire `main.py` pour trouver les autres `include_router` et ajouter après `admin_harpocrate_vaults_router` :

```python
from rag.api.admin_provider_keys import router as admin_provider_keys_router
# ...
app.include_router(admin_provider_keys_router)
```

- [ ] **Lint**

```bash
cd backend
uv run ruff check src/rag/api/admin_provider_keys.py src/rag/main.py
```

- [ ] **Smoke test : vérifier que la route existe**

```bash
uv run python -c "
import os
os.environ.update({'DATABASE_URL': 'postgresql://x:x@localhost/x',
                   'RAG_POSTGRES_ADMIN_URL': 'postgresql://x:x@localhost/x',
                   'RAG_MASTER_KEY': 'x' * 32,
                   'RAG_PUBLIC_URL': 'http://localhost:8000',
                   'RAG_SESSION_SECRET': 'x' * 32})
from rag.main import build_app
from rag.config import Settings
settings = Settings()
app = build_app(settings)
routes = [r.path for r in app.routes]
assert any('provider-keys' in r for r in routes), routes
print('OK')
"
```

Expected: `OK`.

- [ ] **Commit**

```bash
git add backend/src/rag/api/admin_provider_keys.py backend/src/rag/main.py
git commit -m "feat(api): router CRUD provider-keys"
```

---

## Task 5 : Frontend — types + API client

**Files:**
- Modify: `frontend/src/lib/harpocrate-vaults.types.ts`
- Modify: `frontend/src/lib/harpocrate-vaults.ts`

- [ ] **Ajouter les types dans `harpocrate-vaults.types.ts`**

Ajouter à la fin du fichier :

```typescript
export type ProviderApiKey = {
  id: string;
  key_id: string;
  label: string;
  provider: string;
  harpo_path: string;
  created_at: string;
};

export type ProviderApiKeyCreate = {
  key_id: string;
  label: string;
  provider: string;
  value: string;
};

export type ProviderApiKeyUpdate = {
  label?: string;
  value?: string;
};
```

- [ ] **Ajouter les méthodes dans `harpocrate-vaults.ts`**

Ajouter dans `harpocrateVaultsApi` :

```typescript
listProviderKeys: (vaultId: string) =>
  api.get<ProviderApiKey[]>(`${BASE}/${vaultId}/provider-keys`),

createProviderKey: (vaultId: string, payload: ProviderApiKeyCreate) =>
  api.post<ProviderApiKey>(`${BASE}/${vaultId}/provider-keys`, payload),

updateProviderKey: (vaultId: string, keyId: string, payload: ProviderApiKeyUpdate) =>
  api.patch<ProviderApiKey>(`${BASE}/${vaultId}/provider-keys/${keyId}`, payload),

deleteProviderKey: (vaultId: string, keyId: string) =>
  api.delete<void>(`${BASE}/${vaultId}/provider-keys/${keyId}`),
```

- [ ] **TypeScript strict**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -5
```

Expected: no errors.

- [ ] **Commit**

```bash
git add frontend/src/lib/harpocrate-vaults.types.ts frontend/src/lib/harpocrate-vaults.ts
git commit -m "feat(front): types + API client provider_api_keys"
```

---

## Task 6 : Frontend — hooks + i18n

**Files:**
- Modify: `frontend/src/hooks/useHarpocrateVaults.ts`
- Modify: `frontend/src/i18n/fr/harpocrate.json`
- Modify: `frontend/src/i18n/en/harpocrate.json`

- [ ] **Ajouter les hooks dans `useHarpocrateVaults.ts`**

Ajouter les imports nécessaires en tête :
```typescript
import type {
  ProviderApiKeyCreate,
  ProviderApiKeyUpdate,
  // ... imports existants
} from "@/lib/harpocrate-vaults.types";
```

Ajouter les hooks à la fin du fichier :

```typescript
export function useProviderKeys(vaultId: string | null) {
  return useQuery({
    queryKey: [...ROOT_KEY, vaultId, "provider-keys"],
    queryFn: () => harpocrateVaultsApi.listProviderKeys(vaultId as string),
    enabled: !!vaultId,
    staleTime: 30_000,
  });
}

export function useCreateProviderKey(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProviderApiKeyCreate) =>
      harpocrateVaultsApi.createProviderKey(vaultId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "provider-keys"] });
    },
  });
}

export function useUpdateProviderKey(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ keyId, payload }: { keyId: string; payload: ProviderApiKeyUpdate }) =>
      harpocrateVaultsApi.updateProviderKey(vaultId, keyId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "provider-keys"] });
    },
  });
}

export function useDeleteProviderKey(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) =>
      harpocrateVaultsApi.deleteProviderKey(vaultId, keyId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "provider-keys"] });
    },
  });
}
```

- [ ] **Ajouter les clés i18n dans `fr/harpocrate.json`**

Dans la section `"tabs"`, ajouter :
```json
"apikeys": "Clés API"
```

Ajouter une nouvelle section `"apikeys"` :
```json
"apikeys": {
  "add": "Ajouter une clé",
  "empty": "Aucune clé API configurée pour ce coffre.",
  "col_key_id": "ID",
  "col_provider": "Provider",
  "col_label": "Label",
  "replace_btn": "Remplacer",
  "delete_btn": "Supprimer",
  "delete_confirm_title": "Supprimer cette clé ?",
  "delete_confirm_body": "Cette action supprime le secret dans Harpocrate. Elle est irréversible.",
  "delete_referenced_error": "Cette clé est référencée par un workspace et ne peut pas être supprimée.",
  "add_dialog_title": "Nouvelle clé API provider",
  "field_provider": "Provider",
  "field_key_id": "ID (slug)",
  "field_key_id_help": "Lettres, chiffres, - et _ uniquement",
  "field_label": "Label",
  "field_value": "Valeur de la clé",
  "path_preview": "Path Harpocrate :",
  "replace_dialog_title": "Remplacer la valeur",
  "replace_dialog_desc": "La nouvelle valeur remplacera le secret dans Harpocrate au même path.",
  "field_new_value": "Nouvelle valeur",
  "cancel": "Annuler",
  "save": "Enregistrer",
  "replace": "Remplacer",
  "created_toast": "Clé créée avec succès.",
  "replaced_toast": "Valeur remplacée.",
  "deleted_toast": "Clé supprimée.",
  "error_toast": "Une erreur est survenue.",
  "error_duplicate": "Un ID identique existe déjà pour ce provider."
}
```

- [ ] **Ajouter les clés i18n dans `en/harpocrate.json`**

Dans `"tabs"` :
```json
"apikeys": "API Keys"
```

Section `"apikeys"` :
```json
"apikeys": {
  "add": "Add key",
  "empty": "No API keys configured for this vault.",
  "col_key_id": "ID",
  "col_provider": "Provider",
  "col_label": "Label",
  "replace_btn": "Replace",
  "delete_btn": "Delete",
  "delete_confirm_title": "Delete this key?",
  "delete_confirm_body": "This will delete the secret in Harpocrate. This action is irreversible.",
  "delete_referenced_error": "This key is referenced by a workspace and cannot be deleted.",
  "add_dialog_title": "New provider API key",
  "field_provider": "Provider",
  "field_key_id": "ID (slug)",
  "field_key_id_help": "Letters, digits, - and _ only",
  "field_label": "Label",
  "field_value": "Key value",
  "path_preview": "Harpocrate path:",
  "replace_dialog_title": "Replace value",
  "replace_dialog_desc": "The new value will replace the secret in Harpocrate at the same path.",
  "field_new_value": "New value",
  "cancel": "Cancel",
  "save": "Save",
  "replace": "Replace",
  "created_toast": "Key created successfully.",
  "replaced_toast": "Value replaced.",
  "deleted_toast": "Key deleted.",
  "error_toast": "An error occurred.",
  "error_duplicate": "An identical ID already exists for this provider."
}
```

- [ ] **TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -5
```

- [ ] **Commit**

```bash
git add frontend/src/hooks/useHarpocrateVaults.ts frontend/src/i18n/fr/harpocrate.json frontend/src/i18n/en/harpocrate.json
git commit -m "feat(front): hooks useProviderKeys + clés i18n apikeys"
```

---

## Task 7 : Frontend — AddProviderKeyDialog

**Files:**
- Create: `frontend/src/pages/harpocrate/AddProviderKeyDialog.tsx`

- [ ] **Créer le composant**

```tsx
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCreateProviderKey } from "@/hooks/useHarpocrateVaults";
import { useModels } from "@/hooks/useModels";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";

const KEY_ID_RE = /^[a-zA-Z0-9_-]+$/;

interface Props {
  vaultId: string;
  vaultName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddProviderKeyDialog({ vaultId, vaultName, open, onOpenChange }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const { data: models = [] } = useModels();
  const mutation = useCreateProviderKey(vaultId);

  const [provider, setProvider] = useState("");
  const [keyId, setKeyId] = useState("");
  const [label, setLabel] = useState("");
  const [value, setValue] = useState("");
  const [keyIdError, setKeyIdError] = useState("");

  // Providers distincts depuis model_dimensions
  const providers = [...new Set(models.map((m) => m.provider))].sort();

  const harpoPath =
    provider && keyId ? `/${vaultName}/${provider}/${keyId}` : "";

  function validateKeyId(v: string) {
    if (v && !KEY_ID_RE.test(v)) {
      setKeyIdError(t("apikeys.field_key_id_help"));
    } else {
      setKeyIdError("");
    }
  }

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setProvider("");
      setKeyId("");
      setLabel("");
      setValue("");
      setKeyIdError("");
    }
  }

  const canSubmit =
    provider &&
    keyId &&
    KEY_ID_RE.test(keyId) &&
    label.trim() &&
    value.trim() &&
    !mutation.isPending;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    try {
      await mutation.mutateAsync({ key_id: keyId, label, provider, value });
      toast({ title: t("apikeys.created_toast") });
      handleClose(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("apikeys.error_duplicate"), variant: "destructive" });
      } else {
        toast({ title: t("apikeys.error_toast"), variant: "destructive" });
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("apikeys.add_dialog_title")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("apikeys.field_provider")}
            </Label>
            <Select value={provider} onValueChange={setProvider}>
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="openai, voyage, mistral…" />
              </SelectTrigger>
              <SelectContent>
                {providers.map((p) => (
                  <SelectItem key={p} value={p}>
                    {p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("apikeys.field_key_id")}
            </Label>
            <Input
              value={keyId}
              onChange={(e) => {
                setKeyId(e.target.value);
                validateKeyId(e.target.value);
              }}
              placeholder="prod-openai"
              className="mt-1 font-mono"
            />
            {keyIdError ? (
              <p className="mt-1 text-xs text-rose-600">{keyIdError}</p>
            ) : (
              <p className="mt-1 text-xs text-slate-400">{t("apikeys.field_key_id_help")}</p>
            )}
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("apikeys.field_label")}
            </Label>
            <Input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="OpenAI production"
              className="mt-1"
            />
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("apikeys.field_value")}
            </Label>
            <Input
              type="password"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="sk-…"
              className="mt-1 font-mono"
            />
          </div>

          {harpoPath && (
            <div className="rounded bg-slate-50 px-3 py-2 text-xs text-slate-500">
              <span className="font-medium">{t("apikeys.path_preview")}</span>{" "}
              <code className="font-mono">{harpoPath}</code>
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              {t("apikeys.cancel")}
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {t("apikeys.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -5
```

- [ ] **Commit**

```bash
git add frontend/src/pages/harpocrate/AddProviderKeyDialog.tsx
git commit -m "feat(front): AddProviderKeyDialog"
```

---

## Task 8 : Frontend — ReplaceProviderKeyDialog

**Files:**
- Create: `frontend/src/pages/harpocrate/ReplaceProviderKeyDialog.tsx`

- [ ] **Créer le composant**

```tsx
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useUpdateProviderKey } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";

interface Props {
  vaultId: string;
  keyId: string;
  keyLabel: string;
  provider: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ReplaceProviderKeyDialog({
  vaultId,
  keyId,
  keyLabel,
  provider,
  open,
  onOpenChange,
}: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const mutation = useUpdateProviderKey(vaultId);
  const [newValue, setNewValue] = useState("");

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) setNewValue("");
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!newValue.trim()) return;
    try {
      await mutation.mutateAsync({ keyId, payload: { value: newValue } });
      toast({ title: t("apikeys.replaced_toast") });
      handleClose(false);
    } catch {
      toast({ title: t("apikeys.error_toast"), variant: "destructive" });
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("apikeys.replace_dialog_title")}</DialogTitle>
          <DialogDescription>
            {t("apikeys.replace_dialog_desc")}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("apikeys.col_provider")} / {t("apikeys.col_key_id")}
            </Label>
            <Input
              value={`${provider} / ${keyLabel}`}
              disabled
              className="mt-1 font-mono bg-slate-50 text-slate-400"
            />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("apikeys.field_new_value")}
            </Label>
            <Input
              type="password"
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              placeholder="sk-…"
              className="mt-1 font-mono"
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              {t("apikeys.cancel")}
            </Button>
            <Button
              type="submit"
              disabled={mutation.isPending || !newValue.trim()}
            >
              {t("apikeys.replace")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -5
```

- [ ] **Commit**

```bash
git add frontend/src/pages/harpocrate/ReplaceProviderKeyDialog.tsx
git commit -m "feat(front): ReplaceProviderKeyDialog"
```

---

## Task 9 : Frontend — VaultApikeysTab

**Files:**
- Create: `frontend/src/pages/harpocrate/VaultApikeysTab.tsx`

- [ ] **Créer le composant**

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw, Trash2 } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useDeleteProviderKey, useProviderKeys } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";
import type { ProviderApiKey } from "@/lib/harpocrate-vaults.types";
import { ApiError } from "@/lib/api";
import { AddProviderKeyDialog } from "./AddProviderKeyDialog";
import { ReplaceProviderKeyDialog } from "./ReplaceProviderKeyDialog";

interface Props {
  vaultId: string;
  vaultName: string;
}

export function VaultApikeysTab({ vaultId, vaultName }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const { data: keys = [], isLoading } = useProviderKeys(vaultId);
  const deleteMutation = useDeleteProviderKey(vaultId);

  const [addOpen, setAddOpen] = useState(false);
  const [toReplace, setToReplace] = useState<ProviderApiKey | null>(null);
  const [toDelete, setToDelete] = useState<ProviderApiKey | null>(null);

  async function handleDelete() {
    if (!toDelete) return;
    try {
      await deleteMutation.mutateAsync(toDelete.id);
      toast({ title: t("apikeys.deleted_toast") });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("apikeys.delete_referenced_error"), variant: "destructive" });
      } else {
        toast({ title: t("apikeys.error_toast"), variant: "destructive" });
      }
    } finally {
      setToDelete(null);
    }
  }

  return (
    <div className="space-y-4 pt-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setAddOpen(true)}>
          {t("apikeys.add")}
        </Button>
      </div>

      {isLoading ? null : keys.length === 0 ? (
        <div className="rounded border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("apikeys.empty")}
        </div>
      ) : (
        <div className="overflow-hidden rounded border border-slate-200">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("apikeys.col_key_id")}</TableHead>
                <TableHead>{t("apikeys.col_provider")}</TableHead>
                <TableHead>{t("apikeys.col_label")}</TableHead>
                <TableHead className="w-28" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.map((k) => (
                <TableRow key={k.id}>
                  <TableCell className="font-mono text-sm">{k.key_id}</TableCell>
                  <TableCell>
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
                      {k.provider}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm text-slate-600">{k.label}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1 justify-end">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setToReplace(k)}
                        aria-label={t("apikeys.replace_btn")}
                      >
                        <RefreshCw className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setToDelete(k)}
                        className="text-rose-600 hover:text-rose-700"
                        aria-label={t("apikeys.delete_btn")}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <AddProviderKeyDialog
        vaultId={vaultId}
        vaultName={vaultName}
        open={addOpen}
        onOpenChange={setAddOpen}
      />

      {toReplace && (
        <ReplaceProviderKeyDialog
          vaultId={vaultId}
          keyId={toReplace.id}
          keyLabel={toReplace.label}
          provider={toReplace.provider}
          open={!!toReplace}
          onOpenChange={(o) => { if (!o) setToReplace(null); }}
        />
      )}

      <AlertDialog open={!!toDelete} onOpenChange={(o) => { if (!o) setToDelete(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("apikeys.delete_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("apikeys.delete_confirm_body")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("apikeys.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-rose-600 hover:bg-rose-700"
            >
              {t("apikeys.delete_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
```

- [ ] **TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -5
```

- [ ] **Commit**

```bash
git add frontend/src/pages/harpocrate/VaultApikeysTab.tsx
git commit -m "feat(front): VaultApikeysTab"
```

---

## Task 10 : Frontend — VaultDetailPanel + vérification finale

**Files:**
- Modify: `frontend/src/pages/harpocrate/VaultDetailPanel.tsx`

- [ ] **Ajouter l'onglet dans VaultDetailPanel**

Ajouter l'import :
```tsx
import { VaultApikeysTab } from "@/pages/harpocrate/VaultApikeysTab";
```

Dans `<TabsList>`, après `value="info"` :
```tsx
<TabsTrigger value="apikeys">{t("tabs.apikeys")}</TabsTrigger>
```

Dans le contenu des onglets, après `<TabsContent value="info">` :
```tsx
<TabsContent value="apikeys">
  <VaultApikeysTab vaultId={vault.id} vaultName={vault.name} />
</TabsContent>
```

- [ ] **Vérifier TypeScript + lint + tests**

```bash
cd frontend
npx tsc --noEmit
npm run lint
npm run test:run 2>&1 | tail -10
```

Expected: 0 errors, tous les tests PASS.

- [ ] **Vérifier backend complet**

```bash
cd backend
uv run pytest -v --tb=short 2>&1 | tail -20
uv run ruff check src/ tests/
```

Expected: 0 failures, 0 lint errors.

- [ ] **Commit final**

```bash
git add frontend/src/pages/harpocrate/VaultDetailPanel.tsx
git commit -m "feat(front): onglet Apikeys dans VaultDetailPanel"
```
