# Git Credentials — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter une section « Tokens Git » dans l'onglet Apikeys d'un coffre Harpocrate, permettant de stocker des tokens PAT (GitHub, GitLab, Gitea, Bitbucket, Azure DevOps) chiffrés dans Harpocrate.

**Architecture:** Nouvelle table `git_credentials` (migration 025) + service CRUD autonome + router FastAPI, en miroir exact du module `provider_api_keys`. Côté frontend, deux nouvelles sections dans `VaultApikeysTab` avec leurs propres dialogs.

**Tech Stack:** Python 3.12 / asyncpg / FastAPI / Pydantic v2 / pytest-asyncio — React 18 / TypeScript strict / TanStack Query / shadcn/ui / i18next

---

## Structure des fichiers

### Backend (créer)
- `backend/migrations/025_git_credentials.sql`
- `backend/src/rag/schemas/git_credentials.py`
- `backend/src/rag/services/git_credentials.py`
- `backend/src/rag/api/admin_git_credentials.py`
- `backend/tests/integration/test_services_git_credentials.py`

### Backend (modifier)
- `backend/src/rag/main.py` — enregistrer le router

### Frontend (créer)
- `frontend/src/pages/harpocrate/AddGitKeyDialog.tsx`
- `frontend/src/pages/harpocrate/ReplaceGitKeyDialog.tsx`

### Frontend (modifier)
- `frontend/src/lib/harpocrate-vaults.types.ts` — types GitCredential
- `frontend/src/lib/harpocrate-vaults.ts` — fonctions API git
- `frontend/src/hooks/useHarpocrateVaults.ts` — hooks git
- `frontend/src/pages/harpocrate/VaultApikeysTab.tsx` — deux sections
- `frontend/src/i18n/fr/harpocrate.json` — clés gitkeys
- `frontend/src/i18n/en/harpocrate.json` — clés gitkeys

---

## Task 1 : Migration + schemas

**Files:**
- Create: `backend/migrations/025_git_credentials.sql`
- Create: `backend/src/rag/schemas/git_credentials.py`

- [ ] **Écrire la migration**

```sql
-- backend/migrations/025_git_credentials.sql
-- Migration 025 — tokens Git stockés dans Harpocrate

CREATE TABLE git_credentials (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_id     TEXT NOT NULL,
    label      TEXT NOT NULL,
    host       TEXT NOT NULL,
    scope_url  TEXT NULL,
    vault_id   UUID NOT NULL REFERENCES harpocrate_vaults(id) ON DELETE RESTRICT,
    harpo_path TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (vault_id, host, key_id)
);
```

- [ ] **Écrire les schemas Pydantic**

```python
# backend/src/rag/schemas/git_credentials.py
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_KEY_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

GitHost = Literal["github", "gitlab", "gitea", "bitbucket", "azure-devops"]


class GitCredentialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    host: GitHost
    scope_url: str | None = Field(default=None, max_length=512)
    value: str = Field(min_length=1, max_length=4096)

    @field_validator("key_id")
    @classmethod
    def _v_key_id(cls, v: str) -> str:
        if not _KEY_ID_RE.match(v):
            raise ValueError("key_id doit matcher ^[a-zA-Z0-9_-]+$")
        return v


class GitCredentialUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=128)
    scope_url: str | None = Field(default=None, max_length=512)
    value: str | None = Field(default=None, min_length=1, max_length=4096)


class GitCredentialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key_id: str
    label: str
    host: str
    scope_url: str | None
    harpo_path: str
    created_at: datetime
```

- [ ] **Commit**

```bash
git add backend/migrations/025_git_credentials.sql backend/src/rag/schemas/git_credentials.py
git commit -m "feat(db+schemas): migration 025 git_credentials + DTOs"
```

---

## Task 2 : Service git_credentials (TDD)

**Files:**
- Create: `backend/src/rag/services/git_credentials.py`
- Create: `backend/tests/integration/test_services_git_credentials.py`

- [ ] **Écrire les tests (rouge)**

```python
# backend/tests/integration/test_services_git_credentials.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.schemas.git_credentials import GitCredentialCreate, GitCredentialUpdate
from rag.services.git_credentials import (
    DuplicateGitCredentialError,
    GitCredentialNotFoundError,
    GitCredentialReferencedError,
    create_git_credential,
    delete_git_credential,
    list_git_credentials,
    update_git_credential,
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


def _mock_vault_svc(api_key: str = "tok") -> MagicMock:
    svc = MagicMock()
    svc.reveal_api_key = AsyncMock(return_value=api_key)
    return svc


async def test_create_and_list(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool)
    svc = _mock_vault_svc()

    with patch("rag.services.git_credentials.HarpocrateVaultClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        async with pool.acquire() as conn:
            created = await create_git_credential(
                conn,
                vault=vault,
                vault_svc=svc,
                req=GitCredentialCreate(
                    key_id="prod-pat",
                    label="GitHub prod",
                    host="github",
                    value="ghp_test",
                ),
            )

    assert created.key_id == "prod-pat"
    assert created.host == "github"
    assert created.scope_url is None
    assert created.harpo_path == "${vault://v1:/git/github/prod-pat}"
    mock_client.set_secret.assert_called_once_with("/git/github/prod-pat", "ghp_test")

    async with pool.acquire() as conn:
        keys = await list_git_credentials(conn, vault_id=vault["id"])
    assert len(keys) == 1
    assert keys[0].key_id == "prod-pat"


async def test_create_with_scope_url(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v2")
    svc = _mock_vault_svc()

    with patch("rag.services.git_credentials.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await create_git_credential(
                conn,
                vault=vault,
                vault_svc=svc,
                req=GitCredentialCreate(
                    key_id="org-pat",
                    label="GitHub myorg",
                    host="github",
                    scope_url="https://github.com/myorg",
                    value="ghp_test2",
                ),
            )

    assert created.scope_url == "https://github.com/myorg"


async def test_create_duplicate_raises(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v3")
    svc = _mock_vault_svc()

    with patch("rag.services.git_credentials.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            await create_git_credential(
                conn,
                vault=vault,
                vault_svc=svc,
                req=GitCredentialCreate(key_id="dup", label="L", host="gitlab", value="v"),
            )

    with patch("rag.services.git_credentials.HarpocrateVaultClient"):
        with pytest.raises(DuplicateGitCredentialError):
            async with pool.acquire() as conn:
                await create_git_credential(
                    conn,
                    vault=vault,
                    vault_svc=svc,
                    req=GitCredentialCreate(key_id="dup", label="L2", host="gitlab", value="v2"),
                )


async def test_update_label_and_scope(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v4")
    svc = _mock_vault_svc()

    with patch("rag.services.git_credentials.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await create_git_credential(
                conn,
                vault=vault,
                vault_svc=svc,
                req=GitCredentialCreate(key_id="k1", label="Old", host="gitea", value="v"),
            )

    with patch("rag.services.git_credentials.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            updated = await update_git_credential(
                conn,
                key_id=str(created.id),
                vault=vault,
                vault_svc=svc,
                req=GitCredentialUpdate(label="New", scope_url="https://gitea.example.com"),
            )

    assert updated is not None
    assert updated.label == "New"
    assert updated.scope_url == "https://gitea.example.com"


async def test_delete_unreferenced(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v5")
    svc = _mock_vault_svc()

    with patch("rag.services.git_credentials.HarpocrateVaultClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        async with pool.acquire() as conn:
            created = await create_git_credential(
                conn,
                vault=vault,
                vault_svc=svc,
                req=GitCredentialCreate(key_id="del-me", label="L", host="github", value="v"),
            )

    with patch("rag.services.git_credentials.HarpocrateVaultClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        async with pool.acquire() as conn:
            deleted = await delete_git_credential(
                conn,
                key_id=str(created.id),
                vault=vault,
                vault_svc=svc,
            )

    assert deleted is True
    mock_client.delete_secret.assert_called_once()

    async with pool.acquire() as conn:
        keys = await list_git_credentials(conn, vault_id=vault["id"])
    assert keys == []
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/integration/test_services_git_credentials.py -v
```

Résultat attendu : `ImportError` ou `ModuleNotFoundError` (service inexistant).

- [ ] **Implémenter le service**

```python
# backend/src/rag/services/git_credentials.py
from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from rag.schemas.git_credentials import (
    GitCredentialCreate,
    GitCredentialOut,
    GitCredentialUpdate,
)
from rag.secrets.refs import build_ref, parse_ref
from rag.secrets.vault import HarpocrateVaultClient

log = structlog.get_logger(__name__)


class DuplicateGitCredentialError(Exception):
    pass


class GitCredentialNotFoundError(Exception):
    pass


class GitCredentialReferencedError(Exception):
    pass


def _build_secret_path(host: str, key_id: str) -> str:
    return f"/git/{host}/{key_id}"


def _build_vault_ref(vault_name: str, host: str, key_id: str) -> str:
    return build_ref(vault_name, _build_secret_path(host, key_id))


async def _get_vault_client(
    conn: asyncpg.Connection,
    vault: dict[str, Any],
    vault_svc: Any,
) -> HarpocrateVaultClient:
    api_key = await vault_svc.reveal_api_key(conn, UUID(vault["id"]))
    if api_key is None:
        raise RuntimeError("Cannot decrypt vault API key — DEK manquant ?")
    return HarpocrateVaultClient(url=vault["base_url"], token=api_key)


async def list_git_credentials(
    conn: asyncpg.Connection,
    *,
    vault_id: str,
) -> list[GitCredentialOut]:
    rows = await conn.fetch(
        "SELECT id, key_id, label, host, scope_url, harpo_path, created_at "
        "FROM git_credentials WHERE vault_id = $1::uuid "
        "ORDER BY host, key_id",
        vault_id,
    )
    return [GitCredentialOut.model_validate(dict(r)) for r in rows]


async def create_git_credential(
    conn: asyncpg.Connection,
    *,
    vault: dict[str, Any],
    vault_svc: Any,
    req: GitCredentialCreate,
) -> GitCredentialOut:
    secret_path = _build_secret_path(req.host, req.key_id)
    vault_ref = _build_vault_ref(vault["name"], req.host, req.key_id)

    client = await _get_vault_client(conn, vault, vault_svc)
    await asyncio.to_thread(client.set_secret, secret_path, req.value)

    try:
        row = await conn.fetchrow(
            "INSERT INTO git_credentials "
            "(key_id, label, host, scope_url, vault_id, harpo_path) "
            "VALUES ($1, $2, $3, $4, $5::uuid, $6) "
            "RETURNING id, key_id, label, host, scope_url, harpo_path, created_at",
            req.key_id,
            req.label,
            req.host,
            req.scope_url,
            vault["id"],
            vault_ref,
        )
    except asyncpg.UniqueViolationError as exc:
        await asyncio.to_thread(client.delete_secret, secret_path)
        raise DuplicateGitCredentialError(
            f"key_id={req.key_id!r} already exists for host={req.host!r}"
        ) from exc

    log.info("git_credential.created", vault_id=vault["id"], host=req.host, key_id=req.key_id)
    return GitCredentialOut.model_validate(dict(row))


async def update_git_credential(
    conn: asyncpg.Connection,
    *,
    key_id: str,
    vault: dict[str, Any],
    vault_svc: Any,
    req: GitCredentialUpdate,
) -> GitCredentialOut | None:
    row = await conn.fetchrow(
        "SELECT id, key_id, label, host, scope_url, harpo_path, created_at "
        "FROM git_credentials WHERE id = $1::uuid AND vault_id = $2::uuid",
        key_id,
        vault["id"],
    )
    if row is None:
        return None

    if req.value is not None:
        _, secret_path = parse_ref(row["harpo_path"])
        client = await _get_vault_client(conn, vault, vault_svc)
        await asyncio.to_thread(client.set_secret, secret_path, req.value)

    new_label = req.label if req.label is not None else row["label"]
    new_scope_url = req.scope_url if req.scope_url is not None else row["scope_url"]
    updated = await conn.fetchrow(
        "UPDATE git_credentials SET label = $1, scope_url = $2 WHERE id = $3::uuid "
        "RETURNING id, key_id, label, host, scope_url, harpo_path, created_at",
        new_label,
        new_scope_url,
        key_id,
    )
    log.info("git_credential.updated", id=key_id)
    return GitCredentialOut.model_validate(dict(updated))


async def delete_git_credential(
    conn: asyncpg.Connection,
    *,
    key_id: str,
    vault: dict[str, Any],
    vault_svc: Any,
) -> bool:
    row = await conn.fetchrow(
        "SELECT id, harpo_path FROM git_credentials "
        "WHERE id = $1::uuid AND vault_id = $2::uuid",
        key_id,
        vault["id"],
    )
    if row is None:
        return False

    ref_count = await conn.fetchval(
        "SELECT count(*) FROM sources WHERE config->>'auth_ref' LIKE $1",
        f"%{row['harpo_path']}%",
    )
    if int(ref_count or 0) > 0:
        raise GitCredentialReferencedError(
            f"harpo_path={row['harpo_path']!r} referenced in sources"
        )

    _, secret_path = parse_ref(row["harpo_path"])
    client = await _get_vault_client(conn, vault, vault_svc)
    await asyncio.to_thread(client.delete_secret, secret_path)

    await conn.execute("DELETE FROM git_credentials WHERE id = $1::uuid", key_id)
    log.info("git_credential.deleted", id=key_id, harpo_path=row["harpo_path"])
    return True
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/integration/test_services_git_credentials.py -v
```

Résultat attendu : 5 tests PASS.

- [ ] **Commit**

```bash
git add backend/src/rag/services/git_credentials.py \
        backend/tests/integration/test_services_git_credentials.py
git commit -m "feat(services): CRUD git_credentials avec Harpocrate"
```

---

## Task 3 : Router API + enregistrement

**Files:**
- Create: `backend/src/rag/api/admin_git_credentials.py`
- Modify: `backend/src/rag/main.py`

- [ ] **Écrire le router**

```python
# backend/src/rag/api/admin_git_credentials.py
from __future__ import annotations

from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.schemas.git_credentials import (
    GitCredentialCreate,
    GitCredentialOut,
    GitCredentialUpdate,
)
from rag.services.git_credentials import (
    DuplicateGitCredentialError,
    GitCredentialReferencedError,
    create_git_credential,
    delete_git_credential,
    list_git_credentials,
    update_git_credential,
)

log = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/admin/harpocrate-vaults/{vault_id}/git-credentials",
    tags=["admin-git-credentials"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


def _pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pools.config_pool  # type: ignore[no-any-return]


def _vault_svc(request: Request) -> object:
    return request.app.state.harpocrate_vaults_service


@router.get("", response_model=list[GitCredentialOut])
async def list_keys(vault_id: UUID, request: Request) -> list[GitCredentialOut]:
    pool = _pool(request)
    async with pool.acquire() as conn:
        return await list_git_credentials(conn, vault_id=str(vault_id))


@router.post("", response_model=GitCredentialOut, status_code=201)
async def create_key(
    vault_id: UUID,
    body: GitCredentialCreate,
    request: Request,
) -> GitCredentialOut:
    pool = _pool(request)
    svc = _vault_svc(request)
    async with pool.acquire() as conn:
        vault = await svc.get_by_id(conn, vault_id)
        if vault is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
        vault_dict = {"id": str(vault.id), "name": vault.name, "base_url": vault.base_url}
        try:
            return await create_git_credential(conn, vault=vault_dict, vault_svc=svc, req=body)
        except DuplicateGitCredentialError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.patch("/{key_id}", response_model=GitCredentialOut)
async def update_key(
    vault_id: UUID,
    key_id: UUID,
    body: GitCredentialUpdate,
    request: Request,
) -> GitCredentialOut:
    pool = _pool(request)
    svc = _vault_svc(request)
    async with pool.acquire() as conn:
        vault = await svc.get_by_id(conn, vault_id)
        if vault is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
        vault_dict = {"id": str(vault.id), "name": vault.name, "base_url": vault.base_url}
        result = await update_git_credential(
            conn, key_id=str(key_id), vault=vault_dict, vault_svc=svc, req=body
        )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "git credential not found")
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
            deleted = await delete_git_credential(
                conn, key_id=str(key_id), vault=vault_dict, vault_svc=svc
            )
        except GitCredentialReferencedError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "git credential not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Enregistrer le router dans main.py**

Dans `backend/src/rag/main.py`, ajouter après la ligne `from rag.api.admin_provider_keys import router as admin_provider_keys_router` :

```python
from rag.api.admin_git_credentials import router as admin_git_credentials_router
```

Et après `app.include_router(admin_provider_keys_router)` :

```python
app.include_router(admin_git_credentials_router)
```

- [ ] **Vérifier le lint**

```bash
cd backend && uv run ruff check src/rag/api/admin_git_credentials.py src/rag/main.py
```

Résultat attendu : aucune erreur.

- [ ] **Commit**

```bash
git add backend/src/rag/api/admin_git_credentials.py backend/src/rag/main.py
git commit -m "feat(api): router CRUD git-credentials"
```

---

## Task 4 : Frontend — types + API client

**Files:**
- Modify: `frontend/src/lib/harpocrate-vaults.types.ts`
- Modify: `frontend/src/lib/harpocrate-vaults.ts`

- [ ] **Ajouter les types dans harpocrate-vaults.types.ts**

Ajouter à la fin du fichier :

```typescript
export type GitHost =
  | "github"
  | "gitlab"
  | "gitea"
  | "bitbucket"
  | "azure-devops";

export type GitCredential = {
  id: string;
  key_id: string;
  label: string;
  host: GitHost;
  scope_url: string | null;
  harpo_path: string;
  created_at: string;
};

export type GitCredentialCreate = {
  key_id: string;
  label: string;
  host: GitHost;
  scope_url?: string | null;
  value: string;
};

export type GitCredentialUpdate = {
  label?: string;
  scope_url?: string | null;
  value?: string;
};
```

- [ ] **Ajouter les fonctions API dans harpocrate-vaults.ts**

Ajouter les imports nécessaires en tête :

```typescript
import type {
  // ...existants...
  GitCredential,
  GitCredentialCreate,
  GitCredentialUpdate,
} from "@/lib/harpocrate-vaults.types";
```

Ajouter dans l'objet `harpocrateVaultsApi` après `deleteProviderKey` :

```typescript
  listGitCredentials: (vaultId: string) =>
    api.get<GitCredential[]>(`${BASE}/${vaultId}/git-credentials`),

  createGitCredential: (vaultId: string, payload: GitCredentialCreate) =>
    api.post<GitCredential>(`${BASE}/${vaultId}/git-credentials`, payload),

  updateGitCredential: (vaultId: string, keyId: string, payload: GitCredentialUpdate) =>
    api.patch<GitCredential>(`${BASE}/${vaultId}/git-credentials/${keyId}`, payload),

  deleteGitCredential: (vaultId: string, keyId: string) =>
    api.delete<void>(`${BASE}/${vaultId}/git-credentials/${keyId}`),
```

- [ ] **Vérifier TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

Résultat attendu : aucune erreur.

- [ ] **Commit**

```bash
git add frontend/src/lib/harpocrate-vaults.types.ts frontend/src/lib/harpocrate-vaults.ts
git commit -m "feat(front): types + API client git_credentials"
```

---

## Task 5 : Frontend — hooks

**Files:**
- Modify: `frontend/src/hooks/useHarpocrateVaults.ts`

- [ ] **Ajouter les imports en tête du fichier**

Ajouter dans les imports de types existants :

```typescript
import type {
  // ...existants...
  GitCredentialCreate,
  GitCredentialUpdate,
} from "@/lib/harpocrate-vaults.types";
```

- [ ] **Ajouter les hooks à la fin du fichier**

```typescript
export function useGitCredentials(vaultId: string | null) {
  return useQuery({
    queryKey: [...ROOT_KEY, vaultId, "git-credentials"],
    queryFn: () => harpocrateVaultsApi.listGitCredentials(vaultId as string),
    enabled: !!vaultId,
    staleTime: 30_000,
  });
}

export function useCreateGitCredential(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: GitCredentialCreate) =>
      harpocrateVaultsApi.createGitCredential(vaultId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "git-credentials"] });
    },
  });
}

export function useUpdateGitCredential(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ keyId, payload }: { keyId: string; payload: GitCredentialUpdate }) =>
      harpocrateVaultsApi.updateGitCredential(vaultId, keyId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "git-credentials"] });
    },
  });
}

export function useDeleteGitCredential(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) =>
      harpocrateVaultsApi.deleteGitCredential(vaultId, keyId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "git-credentials"] });
    },
  });
}
```

- [ ] **Vérifier TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

Résultat attendu : aucune erreur.

- [ ] **Commit**

```bash
git add frontend/src/hooks/useHarpocrateVaults.ts
git commit -m "feat(front): hooks useGitCredentials"
```

---

## Task 6 : i18n git credentials

**Files:**
- Modify: `frontend/src/i18n/fr/harpocrate.json`
- Modify: `frontend/src/i18n/en/harpocrate.json`

- [ ] **Ajouter les clés FR** (dans `frontend/src/i18n/fr/harpocrate.json`, après le bloc `"apikeys"`)

```json
"gitkeys": {
  "section_title": "Tokens Git",
  "add": "Ajouter un token",
  "empty": "Aucun token Git configuré pour ce coffre.",
  "col_key_id": "ID",
  "col_host": "Host",
  "col_label": "Label",
  "col_scope_url": "Scope URL",
  "replace_btn": "Remplacer",
  "delete_btn": "Supprimer",
  "delete_confirm_title": "Supprimer ce token ?",
  "delete_confirm_body": "Cette action supprime le secret dans Harpocrate. Elle est irréversible.",
  "delete_referenced_error": "Ce token est référencé par une source et ne peut pas être supprimé.",
  "add_dialog_title": "Nouveau token Git",
  "field_host": "Plateforme Git",
  "field_key_id": "ID (slug)",
  "field_key_id_help": "Lettres, chiffres, - et _ uniquement",
  "field_label": "Label",
  "field_scope_url": "Scope URL (optionnel)",
  "field_scope_url_placeholder": "https://github.com/myorg",
  "field_value": "Valeur du token",
  "path_preview": "Path Harpocrate :",
  "replace_dialog_title": "Remplacer la valeur",
  "replace_dialog_desc": "La nouvelle valeur remplacera le secret dans Harpocrate au même path.",
  "field_new_value": "Nouvelle valeur",
  "cancel": "Annuler",
  "save": "Enregistrer",
  "replace": "Remplacer",
  "created_toast": "Token créé avec succès.",
  "replaced_toast": "Valeur remplacée.",
  "deleted_toast": "Token supprimé.",
  "error_toast": "Une erreur est survenue.",
  "error_duplicate": "Un ID identique existe déjà pour ce host."
}
```

- [ ] **Ajouter les clés EN** (dans `frontend/src/i18n/en/harpocrate.json`, après le bloc `"apikeys"`)

```json
"gitkeys": {
  "section_title": "Git Tokens",
  "add": "Add token",
  "empty": "No Git tokens configured for this vault.",
  "col_key_id": "ID",
  "col_host": "Host",
  "col_label": "Label",
  "col_scope_url": "Scope URL",
  "replace_btn": "Replace",
  "delete_btn": "Delete",
  "delete_confirm_title": "Delete this token?",
  "delete_confirm_body": "This will delete the secret in Harpocrate. This action is irreversible.",
  "delete_referenced_error": "This token is referenced by a source and cannot be deleted.",
  "add_dialog_title": "New Git token",
  "field_host": "Git platform",
  "field_key_id": "ID (slug)",
  "field_key_id_help": "Letters, digits, - and _ only",
  "field_label": "Label",
  "field_scope_url": "Scope URL (optional)",
  "field_scope_url_placeholder": "https://github.com/myorg",
  "field_value": "Token value",
  "path_preview": "Harpocrate path:",
  "replace_dialog_title": "Replace value",
  "replace_dialog_desc": "The new value will replace the secret in Harpocrate at the same path.",
  "field_new_value": "New value",
  "cancel": "Cancel",
  "save": "Save",
  "replace": "Replace",
  "created_toast": "Token created successfully.",
  "replaced_toast": "Value replaced.",
  "deleted_toast": "Token deleted.",
  "error_toast": "An error occurred.",
  "error_duplicate": "An identical ID already exists for this host."
}
```

- [ ] **Commit**

```bash
git add frontend/src/i18n/fr/harpocrate.json frontend/src/i18n/en/harpocrate.json
git commit -m "feat(i18n): clés gitkeys harpocrate (fr + en)"
```

---

## Task 7 : AddGitKeyDialog

**Files:**
- Create: `frontend/src/pages/harpocrate/AddGitKeyDialog.tsx`

- [ ] **Créer le composant**

```tsx
// frontend/src/pages/harpocrate/AddGitKeyDialog.tsx
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogContent,
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
import { useCreateGitCredential } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";
import type { GitHost } from "@/lib/harpocrate-vaults.types";

const KEY_ID_RE = /^[a-zA-Z0-9_-]+$/;

const GIT_HOSTS: { value: GitHost; label: string }[] = [
  { value: "github", label: "GitHub" },
  { value: "gitlab", label: "GitLab" },
  { value: "gitea", label: "Gitea" },
  { value: "bitbucket", label: "Bitbucket" },
  { value: "azure-devops", label: "Azure DevOps" },
];

interface Props {
  vaultId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddGitKeyDialog({ vaultId, open, onOpenChange }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const mutation = useCreateGitCredential(vaultId);

  const [host, setHost] = useState<GitHost | "">("");
  const [keyId, setKeyId] = useState("");
  const [label, setLabel] = useState("");
  const [scopeUrl, setScopeUrl] = useState("");
  const [value, setValue] = useState("");
  const [keyIdError, setKeyIdError] = useState("");

  const harpoPath = host && keyId ? `/git/${host}/${keyId}` : "";

  function validateKeyId(v: string) {
    if (v && !KEY_ID_RE.test(v)) {
      setKeyIdError(t("gitkeys.field_key_id_help"));
    } else {
      setKeyIdError("");
    }
  }

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setHost("");
      setKeyId("");
      setLabel("");
      setScopeUrl("");
      setValue("");
      setKeyIdError("");
    }
  }

  const canSubmit =
    !!host &&
    !!keyId &&
    KEY_ID_RE.test(keyId) &&
    label.trim().length > 0 &&
    value.trim().length > 0 &&
    !mutation.isPending;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit || !host) return;
    try {
      await mutation.mutateAsync({
        key_id: keyId,
        label,
        host,
        scope_url: scopeUrl.trim() || null,
        value,
      });
      toast({ title: t("gitkeys.created_toast") });
      handleClose(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("gitkeys.error_duplicate"), variant: "destructive" });
      } else {
        toast({ title: t("gitkeys.error_toast"), variant: "destructive" });
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("gitkeys.add_dialog_title")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("gitkeys.field_host")}
            </Label>
            <Select value={host} onValueChange={(v) => setHost(v as GitHost)}>
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="GitHub, GitLab, Gitea…" />
              </SelectTrigger>
              <SelectContent>
                {GIT_HOSTS.map((h) => (
                  <SelectItem key={h.value} value={h.value}>
                    {h.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("gitkeys.field_key_id")}
            </Label>
            <Input
              value={keyId}
              onChange={(e) => {
                setKeyId(e.target.value);
                validateKeyId(e.target.value);
              }}
              placeholder="prod-pat"
              className="mt-1 font-mono"
            />
            {keyIdError ? (
              <p className="mt-1 text-xs text-rose-600">{keyIdError}</p>
            ) : (
              <p className="mt-1 text-xs text-slate-400">{t("gitkeys.field_key_id_help")}</p>
            )}
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("gitkeys.field_label")}
            </Label>
            <Input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="GitHub myorg production"
              className="mt-1"
            />
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("gitkeys.field_scope_url")}
            </Label>
            <Input
              value={scopeUrl}
              onChange={(e) => setScopeUrl(e.target.value)}
              placeholder={t("gitkeys.field_scope_url_placeholder")}
              className="mt-1"
            />
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("gitkeys.field_value")}
            </Label>
            <Input
              type="password"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="ghp_…"
              className="mt-1 font-mono"
            />
          </div>

          {harpoPath && (
            <div className="rounded bg-slate-50 px-3 py-2 text-xs text-slate-500">
              <span className="font-medium">{t("gitkeys.path_preview")}</span>{" "}
              <code className="font-mono">{harpoPath}</code>
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              {t("gitkeys.cancel")}
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {t("gitkeys.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Vérifier TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

Résultat attendu : aucune erreur.

- [ ] **Commit**

```bash
git add frontend/src/pages/harpocrate/AddGitKeyDialog.tsx
git commit -m "feat(front): AddGitKeyDialog"
```

---

## Task 8 : ReplaceGitKeyDialog

**Files:**
- Create: `frontend/src/pages/harpocrate/ReplaceGitKeyDialog.tsx`

- [ ] **Créer le composant**

```tsx
// frontend/src/pages/harpocrate/ReplaceGitKeyDialog.tsx
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
import { useUpdateGitCredential } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";

interface Props {
  vaultId: string;
  keyId: string;
  keyLabel: string;
  host: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ReplaceGitKeyDialog({
  vaultId,
  keyId,
  keyLabel,
  host,
  open,
  onOpenChange,
}: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const mutation = useUpdateGitCredential(vaultId);
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
      toast({ title: t("gitkeys.replaced_toast") });
      handleClose(false);
    } catch {
      toast({ title: t("gitkeys.error_toast"), variant: "destructive" });
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("gitkeys.replace_dialog_title")}</DialogTitle>
          <DialogDescription>{t("gitkeys.replace_dialog_desc")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("gitkeys.col_host")} / {t("gitkeys.col_key_id")}
            </Label>
            <Input
              value={`${host} / ${keyLabel}`}
              disabled
              className="mt-1 font-mono bg-slate-50 text-slate-400"
            />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("gitkeys.field_new_value")}
            </Label>
            <Input
              type="password"
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              placeholder="ghp_…"
              className="mt-1 font-mono"
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              {t("gitkeys.cancel")}
            </Button>
            <Button type="submit" disabled={mutation.isPending || !newValue.trim()}>
              {t("gitkeys.replace")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Vérifier TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

Résultat attendu : aucune erreur.

- [ ] **Commit**

```bash
git add frontend/src/pages/harpocrate/ReplaceGitKeyDialog.tsx
git commit -m "feat(front): ReplaceGitKeyDialog"
```

---

## Task 9 : Mise à jour VaultApikeysTab

**Files:**
- Modify: `frontend/src/pages/harpocrate/VaultApikeysTab.tsx`

- [ ] **Réécrire VaultApikeysTab avec deux sections**

Remplacer le contenu entier du fichier par :

```tsx
// frontend/src/pages/harpocrate/VaultApikeysTab.tsx
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
import {
  useDeleteProviderKey,
  useDeleteGitCredential,
  useGitCredentials,
  useProviderKeys,
} from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";
import type { GitCredential, ProviderApiKey } from "@/lib/harpocrate-vaults.types";
import { ApiError } from "@/lib/api";
import { AddProviderKeyDialog } from "./AddProviderKeyDialog";
import { ReplaceProviderKeyDialog } from "./ReplaceProviderKeyDialog";
import { AddGitKeyDialog } from "./AddGitKeyDialog";
import { ReplaceGitKeyDialog } from "./ReplaceGitKeyDialog";

interface Props {
  vaultId: string;
}

export function VaultApikeysTab({ vaultId }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();

  // Provider keys state
  const { data: providerKeys = [], isLoading: loadingProvider } = useProviderKeys(vaultId);
  const deleteProviderMutation = useDeleteProviderKey(vaultId);
  const [addProviderOpen, setAddProviderOpen] = useState(false);
  const [toReplaceProvider, setToReplaceProvider] = useState<ProviderApiKey | null>(null);
  const [toDeleteProvider, setToDeleteProvider] = useState<ProviderApiKey | null>(null);

  // Git credentials state
  const { data: gitKeys = [], isLoading: loadingGit } = useGitCredentials(vaultId);
  const deleteGitMutation = useDeleteGitCredential(vaultId);
  const [addGitOpen, setAddGitOpen] = useState(false);
  const [toReplaceGit, setToReplaceGit] = useState<GitCredential | null>(null);
  const [toDeleteGit, setToDeleteGit] = useState<GitCredential | null>(null);

  async function handleDeleteProvider() {
    if (!toDeleteProvider) return;
    try {
      await deleteProviderMutation.mutateAsync(toDeleteProvider.id);
      toast({ title: t("apikeys.deleted_toast") });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("apikeys.delete_referenced_error"), variant: "destructive" });
      } else {
        toast({ title: t("apikeys.error_toast"), variant: "destructive" });
      }
    } finally {
      setToDeleteProvider(null);
    }
  }

  async function handleDeleteGit() {
    if (!toDeleteGit) return;
    try {
      await deleteGitMutation.mutateAsync(toDeleteGit.id);
      toast({ title: t("gitkeys.deleted_toast") });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("gitkeys.delete_referenced_error"), variant: "destructive" });
      } else {
        toast({ title: t("gitkeys.error_toast"), variant: "destructive" });
      }
    } finally {
      setToDeleteGit(null);
    }
  }

  return (
    <div className="space-y-8 pt-4">
      {/* ─── Section Clés IA ─────────────────────────────────── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-700">{t("tabs.apikeys")}</h3>
          <Button size="sm" onClick={() => setAddProviderOpen(true)}>
            {t("apikeys.add")}
          </Button>
        </div>

        {!loadingProvider && providerKeys.length === 0 ? (
          <div className="rounded border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
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
                {providerKeys.map((k) => (
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
                          onClick={() => setToReplaceProvider(k)}
                          aria-label={t("apikeys.replace_btn")}
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setToDeleteProvider(k)}
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
      </div>

      {/* ─── Section Tokens Git ──────────────────────────────── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-700">{t("gitkeys.section_title")}</h3>
          <Button size="sm" variant="outline" onClick={() => setAddGitOpen(true)}>
            {t("gitkeys.add")}
          </Button>
        </div>

        {!loadingGit && gitKeys.length === 0 ? (
          <div className="rounded border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
            {t("gitkeys.empty")}
          </div>
        ) : (
          <div className="overflow-hidden rounded border border-slate-200">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("gitkeys.col_key_id")}</TableHead>
                  <TableHead>{t("gitkeys.col_host")}</TableHead>
                  <TableHead>{t("gitkeys.col_label")}</TableHead>
                  <TableHead>{t("gitkeys.col_scope_url")}</TableHead>
                  <TableHead className="w-28" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {gitKeys.map((k) => (
                  <TableRow key={k.id}>
                    <TableCell className="font-mono text-sm">{k.key_id}</TableCell>
                    <TableCell>
                      <span className="rounded bg-sky-100 px-2 py-0.5 text-xs font-medium text-sky-700">
                        {k.host}
                      </span>
                    </TableCell>
                    <TableCell className="text-sm text-slate-600">{k.label}</TableCell>
                    <TableCell className="text-xs text-slate-400 font-mono">
                      {k.scope_url ?? "—"}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1 justify-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setToReplaceGit(k)}
                          aria-label={t("gitkeys.replace_btn")}
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setToDeleteGit(k)}
                          className="text-rose-600 hover:text-rose-700"
                          aria-label={t("gitkeys.delete_btn")}
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
      </div>

      {/* ─── Dialogs Provider ────────────────────────────────── */}
      <AddProviderKeyDialog
        vaultId={vaultId}
        open={addProviderOpen}
        onOpenChange={setAddProviderOpen}
      />

      {toReplaceProvider && (
        <ReplaceProviderKeyDialog
          vaultId={vaultId}
          keyId={toReplaceProvider.id}
          keyLabel={toReplaceProvider.label}
          provider={toReplaceProvider.provider}
          open={!!toReplaceProvider}
          onOpenChange={(o) => { if (!o) setToReplaceProvider(null); }}
        />
      )}

      <AlertDialog
        open={!!toDeleteProvider}
        onOpenChange={(o) => { if (!o) setToDeleteProvider(null); }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("apikeys.delete_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>{t("apikeys.delete_confirm_body")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("apikeys.cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteProvider} className="bg-rose-600 hover:bg-rose-700">
              {t("apikeys.delete_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* ─── Dialogs Git ─────────────────────────────────────── */}
      <AddGitKeyDialog
        vaultId={vaultId}
        open={addGitOpen}
        onOpenChange={setAddGitOpen}
      />

      {toReplaceGit && (
        <ReplaceGitKeyDialog
          vaultId={vaultId}
          keyId={toReplaceGit.id}
          keyLabel={toReplaceGit.label}
          host={toReplaceGit.host}
          open={!!toReplaceGit}
          onOpenChange={(o) => { if (!o) setToReplaceGit(null); }}
        />
      )}

      <AlertDialog
        open={!!toDeleteGit}
        onOpenChange={(o) => { if (!o) setToDeleteGit(null); }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("gitkeys.delete_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>{t("gitkeys.delete_confirm_body")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("gitkeys.cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteGit} className="bg-rose-600 hover:bg-rose-700">
              {t("gitkeys.delete_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
```

- [ ] **Vérifier TypeScript + lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Résultat attendu : aucune erreur.

- [ ] **Commit**

```bash
git add frontend/src/pages/harpocrate/VaultApikeysTab.tsx
git commit -m "feat(front): VaultApikeysTab — deux sections provider + git"
```
