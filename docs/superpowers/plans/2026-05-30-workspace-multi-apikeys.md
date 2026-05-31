# Multi-clés API Workspace — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer la clé API unique par workspace par un système multi-clés avec nom, révocation et rotation (grace period 72h).

**Architecture:** Nouvelle table `workspace_api_keys` remplace `workspaces.api_key_fingerprint` + `workspaces.api_key_ref`. L'auth MCP lit dans `workspace_api_keys`. Chaque clé a son propre path Harpocrate `wsapi_{name}/{key_id}`. La création de workspace génère automatiquement une clé "default".

**Tech Stack:** Python 3.12 / asyncpg / FastAPI — React 18 / TypeScript strict / TanStack Query

---

## Structure des fichiers

### Backend (créer)
- `backend/migrations/033_workspace_api_keys.sql`
- `backend/src/rag/schemas/workspace_apikeys.py`
- `backend/src/rag/services/workspace_apikeys.py`

### Backend (modifier)
- `backend/src/rag/services/workspaces.py` — create_workspace sans api_key_fingerprint/api_key_ref
- `backend/src/rag/services/mcp.py` — _authenticate utilise workspace_api_keys
- `backend/src/rag/api/admin.py` — nouveaux endpoints + retirer rotate_apikey
- `backend/schema/schema_v1.sql` — mettre à jour le schéma consolidé

### Frontend (créer)
- `frontend/src/lib/workspace-apikeys.types.ts`
- `frontend/src/lib/workspace-apikeys.ts`
- `frontend/src/hooks/useWorkspaceApiKeys.ts`
- `frontend/src/i18n/fr/apikeys.json`
- `frontend/src/i18n/en/apikeys.json`
- `frontend/src/pages/workspace/WorkspaceApiKeysTab.tsx`
- `frontend/src/pages/workspace/CreateApiKeyDialog.tsx`
- `frontend/src/pages/workspace/RotateApiKeyDialog.tsx`

### Frontend (modifier)
- `frontend/src/lib/i18n.ts` — namespace apikeys
- `frontend/src/i18n/fr/workspace.json` — clé tabs.apikeys
- `frontend/src/i18n/en/workspace.json` — idem
- `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx` — onglet API Keys

---

## Task 1 : Migration 033

**Files:**
- Create: `backend/migrations/033_workspace_api_keys.sql`

- [ ] **Créer la migration**

```sql
-- backend/migrations/033_workspace_api_keys.sql
-- Migration 033 — multi-clés API par workspace

CREATE TABLE workspace_api_keys (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    fingerprint  TEXT NOT NULL,
    api_key_ref  TEXT NOT NULL,
    revoked_at   TIMESTAMPTZ,
    rotated_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, fingerprint)
);

CREATE INDEX workspace_api_keys_ws ON workspace_api_keys (workspace_id);
CREATE INDEX workspace_api_keys_fp ON workspace_api_keys (fingerprint);

ALTER TABLE workspaces DROP COLUMN IF EXISTS api_key_fingerprint;
ALTER TABLE workspaces DROP COLUMN IF EXISTS api_key_ref;
```

- [ ] **Commit**

```bash
git add backend/migrations/033_workspace_api_keys.sql
git commit -m "feat(db): migration 033 workspace_api_keys — multi-clés avec grace period"
```

---

## Task 2 : Schemas + Service workspace_apikeys.py

**Files:**
- Create: `backend/src/rag/schemas/workspace_apikeys.py`
- Create: `backend/src/rag/services/workspace_apikeys.py`

- [ ] **Créer `backend/src/rag/schemas/workspace_apikeys.py`**

```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_GRACE_HOURS = 72


class ApiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    fingerprint_preview: str      # 8 premiers chars du fingerprint
    api_key_ref: str
    status: str                   # "active" | "grace_period" | "revoked" | "expired"
    created_at: datetime
    revoked_at: datetime | None
    rotated_at: datetime | None


class ApiKeyCreated(BaseModel):
    id: UUID
    name: str
    fingerprint_preview: str
    api_key: str                   # en clair, une seule fois
    created_at: datetime


class ApiKeyRotated(BaseModel):
    new_key_id: UUID
    new_api_key: str               # en clair, une seule fois
    new_fingerprint_preview: str
    old_key_id: UUID
    grace_until: datetime          # rotated_at + 72h
```

- [ ] **Créer `backend/src/rag/services/workspace_apikeys.py`**

```python
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from rag.schemas.workspace_apikeys import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    ApiKeyRotated,
)
from rag.secrets.refs import build_ref, parse_ref

log = structlog.get_logger(__name__)

_GRACE_HOURS = 72

_STATUS_SQL = """
    CASE
        WHEN revoked_at IS NOT NULL THEN 'revoked'
        WHEN rotated_at IS NOT NULL AND rotated_at <= now() - interval '72 hours' THEN 'expired'
        WHEN rotated_at IS NOT NULL THEN 'grace_period'
        ELSE 'active'
    END AS status
"""


def _key_path(workspace_name: str, key_id: str) -> str:
    return f"wsapi_{workspace_name}/{key_id}"


async def _get_vault_client(vault_svc: Any, client_provider: Any, config_pool: asyncpg.Pool):
    async with config_pool.acquire() as conn:
        vault = await vault_svc.get_default(conn)
    if vault is None:
        raise RuntimeError("no default Harpocrate vault configured")
    client = await client_provider.get_client(vault.api_key_id)
    return vault, client


async def list_keys(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
) -> list[ApiKeyOut]:
    rows = await conn.fetch(
        f"""
        SELECT k.id, k.name, k.fingerprint, k.api_key_ref,
               k.created_at, k.revoked_at, k.rotated_at,
               {_STATUS_SQL}
        FROM workspace_api_keys k
        JOIN workspaces w ON w.id = k.workspace_id
        WHERE w.name = $1
        ORDER BY k.created_at DESC
        """,
        workspace_name,
    )
    return [
        ApiKeyOut(
            id=r["id"],
            name=r["name"],
            fingerprint_preview=r["fingerprint"][:8],
            api_key_ref=r["api_key_ref"],
            status=r["status"],
            created_at=r["created_at"],
            revoked_at=r["revoked_at"],
            rotated_at=r["rotated_at"],
        )
        for r in rows
    ]


async def create_key(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    req: ApiKeyCreate,
    vault_svc: Any,
    client_provider: Any,
    config_pool: asyncpg.Pool,
) -> ApiKeyCreated:
    from rag.services.apikey import generate_api_key

    ws_id = await conn.fetchval(
        "SELECT id FROM workspaces WHERE name = $1", workspace_name
    )
    if ws_id is None:
        raise ValueError(f"workspace {workspace_name!r} not found")

    api_key = generate_api_key()
    fp = sha256(api_key.encode()).hexdigest()

    # Réserver l'ID avant d'écrire dans Harpocrate
    key_id = await conn.fetchval(
        """
        INSERT INTO workspace_api_keys (workspace_id, name, fingerprint, api_key_ref)
        VALUES ($1, $2, $3, 'pending')
        RETURNING id
        """,
        ws_id, req.name, fp,
    )

    vault, client = await _get_vault_client(vault_svc, client_provider, config_pool)
    path = _key_path(workspace_name, str(key_id))
    api_key_ref = build_ref(vault.api_key_id, path)

    await asyncio.to_thread(client.set_secret, path, api_key)

    row = await conn.fetchrow(
        """
        UPDATE workspace_api_keys SET api_key_ref = $1
        WHERE id = $2
        RETURNING id, name, fingerprint, created_at
        """,
        api_key_ref, key_id,
    )

    log.info("workspace_api_key.created", workspace=workspace_name, name=req.name)
    return ApiKeyCreated(
        id=row["id"],
        name=row["name"],
        fingerprint_preview=row["fingerprint"][:8],
        api_key=api_key,
        created_at=row["created_at"],
    )


async def rotate_key(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    key_id: str,
    vault_svc: Any,
    client_provider: Any,
    config_pool: asyncpg.Pool,
) -> ApiKeyRotated:
    from rag.services.apikey import generate_api_key

    old_row = await conn.fetchrow(
        """
        SELECT k.id, k.api_key_ref, k.revoked_at
        FROM workspace_api_keys k
        JOIN workspaces w ON w.id = k.workspace_id
        WHERE w.name = $1 AND k.id = $2::uuid
        """,
        workspace_name, key_id,
    )
    if old_row is None:
        return None  # type: ignore[return-value]
    if old_row["revoked_at"] is not None:
        raise ValueError("cannot rotate a revoked key")

    ws_id = await conn.fetchval(
        "SELECT id FROM workspaces WHERE name = $1", workspace_name
    )
    new_api_key = generate_api_key()
    new_fp = sha256(new_api_key.encode()).hexdigest()

    new_key_id = await conn.fetchval(
        """
        INSERT INTO workspace_api_keys (workspace_id, name, fingerprint, api_key_ref)
        SELECT workspace_id, name || ' (rotation)', $2, 'pending'
        FROM workspace_api_keys WHERE id = $1::uuid
        RETURNING id
        """,
        key_id, new_fp,
    )

    vault, client = await _get_vault_client(vault_svc, client_provider, config_pool)
    path = _key_path(workspace_name, str(new_key_id))
    new_api_key_ref = build_ref(vault.api_key_id, path)

    await asyncio.to_thread(client.set_secret, path, new_api_key)

    now = datetime.now(UTC)
    await conn.execute(
        "UPDATE workspace_api_keys SET api_key_ref = $1 WHERE id = $2",
        new_api_key_ref, new_key_id,
    )
    await conn.execute(
        "UPDATE workspace_api_keys SET rotated_at = $1 WHERE id = $2::uuid",
        now, key_id,
    )

    log.info("workspace_api_key.rotated", workspace=workspace_name, old=key_id)
    return ApiKeyRotated(
        new_key_id=new_key_id,
        new_api_key=new_api_key,
        new_fingerprint_preview=new_fp[:8],
        old_key_id=UUID(key_id),
        grace_until=now + timedelta(hours=_GRACE_HOURS),
    )


async def revoke_key(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    key_id: str,
) -> bool:
    result = await conn.execute(
        """
        UPDATE workspace_api_keys k SET revoked_at = now()
        FROM workspaces w
        WHERE w.id = k.workspace_id AND w.name = $1 AND k.id = $2::uuid
          AND k.revoked_at IS NULL
        """,
        workspace_name, key_id,
    )
    return result != "UPDATE 0"
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/schemas/workspace_apikeys.py src/rag/services/workspace_apikeys.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/schemas/workspace_apikeys.py \
        backend/src/rag/services/workspace_apikeys.py
git commit -m "feat(schemas+services): workspace_api_keys — CRUD multi-clés avec grace period"
```

---

## Task 3 : Mettre à jour workspaces.py + mcp.py

**Files:**
- Modify: `backend/src/rag/services/workspaces.py`
- Modify: `backend/src/rag/services/mcp.py`

- [ ] **Lire `backend/src/rag/services/workspaces.py` entièrement**

- [ ] **Modifier `create_workspace` dans `workspaces.py`**

Supprimer :
- La génération de `api_key`, `fingerprint`, `ws_path`, `api_key_ref`
- L'écriture du secret Harpocrate (`write_secret`) pour le workspace
- Le `_rollback_harpocrate`
- Les colonnes `api_key_ref`, `api_key_fingerprint` dans l'INSERT workspaces

Remplacer le bloc INSERT workspaces par :

```python
ws_row = await conn.fetchrow(
    """
    INSERT INTO workspaces
        (name, rag_cnx, rag_base)
    VALUES
        ($1, $2, $3)
    RETURNING id, created_at
    """,
    request.name,
    rag_cnx,
    rag_base,
)
```

Après la transaction (workspace + indexer créés avec succès), créer la première clé :

```python
from rag.schemas.workspace_apikeys import ApiKeyCreate
from rag.services.workspace_apikeys import create_key as _create_ws_key

async with config_pool.acquire() as conn:
    first_key = await _create_ws_key(
        conn,
        workspace_name=request.name,
        req=ApiKeyCreate(name="default"),
        vault_svc=harpocrate_vaults_service,
        client_provider=None,  # passé via paramètre
        config_pool=config_pool,
    )
```

**Note** : `create_workspace` doit recevoir `client_provider` en paramètre. Lis la signature actuelle et ajoute-le.

Le retour final utilise `first_key.api_key` à la place de l'ancien `api_key` :

```python
return {
    "id": str(ws_row["id"]),
    "name": request.name,
    "api_key": first_key.api_key,
    "created_at": ws_row["created_at"].isoformat(),
}
```

Supprimer entièrement la fonction `rotate_apikey` (remplacée par le service workspace_apikeys).

- [ ] **Modifier `_authenticate` dans `mcp.py`**

Remplacer le SELECT existant (qui utilise `w.api_key_fingerprint`) par :

```python
fingerprint = sha256(ref.api_key.encode("utf-8")).hexdigest()

row = await config_pool.fetchrow(
    """
    SELECT w.id,
           k.api_key_ref,
           ic.provider || '/' || ic.model AS indexer_used
    FROM workspaces w
    JOIN workspace_api_keys k ON k.workspace_id = w.id
    JOIN indexer_configs ic ON ic.workspace_id = w.id
    WHERE w.name = $1
      AND k.fingerprint = $2
      AND k.revoked_at IS NULL
      AND (k.rotated_at IS NULL OR k.rotated_at > now() - interval '72 hours')
    """,
    ref.name,
    fingerprint,
)
```

Le reste de `_authenticate` (cache, comparaison timing-safe via Harpocrate) reste identique.

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/services/workspaces.py src/rag/services/mcp.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/services/workspaces.py backend/src/rag/services/mcp.py
git commit -m "feat(services): create_workspace multi-keys + mcp auth via workspace_api_keys"
```

---

## Task 4 : Router admin — nouveaux endpoints API keys

**Files:**
- Modify: `backend/src/rag/api/admin.py`

- [ ] **Lire `backend/src/rag/api/admin.py`** — trouver `rotate_apikey_endpoint` et `get_apikey_endpoint`

- [ ] **Modifier `admin.py`**

**1. Supprimer `rotate_apikey_endpoint`** (POST /workspaces/{name}/rotate-apikey).

**2. Mettre à jour `get_apikey_endpoint`** pour utiliser la première clé active :

```python
@router.get("/workspaces/{name}/apikey")
async def get_apikey_endpoint(name: str, request: Request) -> ApiKeyRotateResponse:
    """Retourne la clé default pour init-rag.sh (compat)."""
    pool = _config_pool(request)
    vault_svc = request.app.state.harpocrate_vaults_service
    client_provider = request.app.state.client_provider
    cache = request.app.state.apikey_cache

    row = await pool.fetchrow(
        """
        SELECT k.api_key_ref FROM workspace_api_keys k
        JOIN workspaces w ON w.id = k.workspace_id
        WHERE w.name = $1 AND k.revoked_at IS NULL
          AND (k.rotated_at IS NULL OR k.rotated_at > now() - interval '72 hours')
        ORDER BY k.created_at ASC LIMIT 1
        """,
        name,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no active api key")
    api_key_ref: str = row["api_key_ref"]
    cached = cache.get(api_key_ref)
    if cached is None:
        try:
            cached = await request.app.state.resolver.resolve_with_retry(api_key_ref)
        except Exception as e:
            raise HarpocrateUnreachableForApikey() from e
        cache.put(api_key_ref, cached)
    return ApiKeyRotateResponse(api_key=cached)
```

**3. Ajouter les nouveaux endpoints** dans `build_admin_router()` :

```python
from rag.schemas.workspace_apikeys import ApiKeyCreate, ApiKeyCreated, ApiKeyOut, ApiKeyRotated

@router.get("/workspaces/{name}/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(name: str, request: Request) -> list[ApiKeyOut]:
    from rag.services.workspace_apikeys import list_keys
    async with _config_pool(request).acquire() as conn:
        return await list_keys(conn, workspace_name=name)

@router.post("/workspaces/{name}/api-keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    name: str, body: ApiKeyCreate, request: Request
) -> ApiKeyCreated:
    from rag.services.workspace_apikeys import create_key
    pool = _config_pool(request)
    async with pool.acquire() as conn:
        try:
            return await create_key(
                conn,
                workspace_name=name,
                req=body,
                vault_svc=request.app.state.harpocrate_vaults_service,
                client_provider=request.app.state.client_provider,
                config_pool=pool,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

@router.post("/workspaces/{name}/api-keys/{key_id}/rotate", response_model=ApiKeyRotated)
async def rotate_api_key(
    name: str, key_id: UUID, request: Request
) -> ApiKeyRotated:
    from rag.services.workspace_apikeys import rotate_key
    pool = _config_pool(request)
    async with pool.acquire() as conn:
        result = await rotate_key(
            conn,
            workspace_name=name,
            key_id=str(key_id),
            vault_svc=request.app.state.harpocrate_vaults_service,
            client_provider=request.app.state.client_provider,
            config_pool=pool,
        )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "api key not found")
    return result

@router.delete("/workspaces/{name}/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    name: str, key_id: UUID, request: Request
) -> Response:
    from rag.services.workspace_apikeys import revoke_key
    async with _config_pool(request).acquire() as conn:
        revoked = await revoke_key(conn, workspace_name=name, key_id=str(key_id))
    if not revoked:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "api key not found or already revoked")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

**4. Mettre à jour `post_workspaces`** pour passer `client_provider` à `create_workspace` :

```python
resp = await create_workspace(
    request=payload,
    config_pool=_config_pool(request),
    admin_dsn=_admin_dsn(request),
    resolver=_resolver(request),
    harpocrate_vaults_service=request.app.state.harpocrate_vaults_service,
    client_provider=request.app.state.client_provider,
)
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/api/admin.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/api/admin.py
git commit -m "feat(api): workspace multi-clés — GET/POST/rotate/revoke + compat get_apikey"
```

---

## Task 5 : Frontend — types + API + hooks + i18n

**Files:**
- Create: `frontend/src/lib/workspace-apikeys.types.ts`
- Create: `frontend/src/lib/workspace-apikeys.ts`
- Create: `frontend/src/hooks/useWorkspaceApiKeys.ts`
- Create: `frontend/src/i18n/fr/apikeys.json`
- Create: `frontend/src/i18n/en/apikeys.json`
- Modify: `frontend/src/lib/i18n.ts`
- Modify: `frontend/src/i18n/fr/workspace.json`
- Modify: `frontend/src/i18n/en/workspace.json`

- [ ] **Créer `frontend/src/lib/workspace-apikeys.types.ts`**

```typescript
export type ApiKeyStatus = "active" | "grace_period" | "revoked" | "expired";

export type ApiKey = {
  id: string;
  name: string;
  fingerprint_preview: string;
  api_key_ref: string;
  status: ApiKeyStatus;
  created_at: string;
  revoked_at: string | null;
  rotated_at: string | null;
};

export type ApiKeyCreate = {
  name: string;
};

export type ApiKeyCreated = {
  id: string;
  name: string;
  fingerprint_preview: string;
  api_key: string;
  created_at: string;
};

export type ApiKeyRotated = {
  new_key_id: string;
  new_api_key: string;
  new_fingerprint_preview: string;
  old_key_id: string;
  grace_until: string;
};
```

- [ ] **Créer `frontend/src/lib/workspace-apikeys.ts`**

```typescript
import { api } from "@/lib/api";
import type {
  ApiKey,
  ApiKeyCreate,
  ApiKeyCreated,
  ApiKeyRotated,
} from "@/lib/workspace-apikeys.types";

const BASE = (name: string) => `/api/admin/workspaces/${name}/api-keys`;

export const workspaceApiKeysApi = {
  list: (workspaceName: string) =>
    api.get<ApiKey[]>(BASE(workspaceName)),

  create: (workspaceName: string, payload: ApiKeyCreate) =>
    api.post<ApiKeyCreated>(BASE(workspaceName), payload),

  rotate: (workspaceName: string, keyId: string) =>
    api.post<ApiKeyRotated>(`${BASE(workspaceName)}/${keyId}/rotate`, {}),

  revoke: (workspaceName: string, keyId: string) =>
    api.delete<void>(`${BASE(workspaceName)}/${keyId}`),
};
```

- [ ] **Créer `frontend/src/hooks/useWorkspaceApiKeys.ts`**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { workspaceApiKeysApi } from "@/lib/workspace-apikeys";
import type { ApiKeyCreate } from "@/lib/workspace-apikeys.types";

const KEY = (ws: string) => ["workspace-api-keys", ws] as const;

export function useWorkspaceApiKeys(workspaceName: string) {
  return useQuery({
    queryKey: KEY(workspaceName),
    queryFn: () => workspaceApiKeysApi.list(workspaceName),
    staleTime: 30_000,
  });
}

export function useCreateApiKey(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ApiKeyCreate) =>
      workspaceApiKeysApi.create(workspaceName, payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY(workspaceName) }),
  });
}

export function useRotateApiKey(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) =>
      workspaceApiKeysApi.rotate(workspaceName, keyId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY(workspaceName) }),
  });
}

export function useRevokeApiKey(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) =>
      workspaceApiKeysApi.revoke(workspaceName, keyId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY(workspaceName) }),
  });
}
```

- [ ] **Créer `frontend/src/i18n/fr/apikeys.json`**

```json
{
  "tab": "API Keys",
  "add_btn": "Créer une clé",
  "empty": "Aucune clé API. Créez-en une pour accéder à ce workspace.",
  "col_name": "Nom",
  "col_fingerprint": "Fingerprint",
  "col_status": "Statut",
  "col_created": "Créée le",
  "status_active": "Active",
  "status_grace_period": "Grace {{hours}}h",
  "status_revoked": "Révoquée",
  "status_expired": "Expirée",
  "rotate_btn": "Rotation",
  "revoke_btn": "Révoquer",
  "revoke_confirm_title": "Révoquer cette clé ?",
  "revoke_confirm_body": "La clé sera immédiatement invalide. Action irréversible.",
  "revoked_toast": "Clé révoquée.",
  "create_dialog_title": "Créer une clé API",
  "field_name": "Nom",
  "field_name_placeholder": "Production, CI/CD agent…",
  "create_save": "Créer",
  "created_key_title": "Clé créée — copiez-la maintenant",
  "created_key_warning": "Cette clé ne sera plus affichée. Copiez-la avant de fermer.",
  "copy_btn": "Copier",
  "copied_toast": "Clé copiée.",
  "close": "Fermer",
  "rotate_dialog_title": "Rotation de clé",
  "rotate_confirm": "Une nouvelle clé sera générée. L'ancienne restera valide 72 heures.",
  "rotate_save": "Effectuer la rotation",
  "rotated_new_key_title": "Nouvelle clé — copiez-la maintenant",
  "grace_info": "L'ancienne clé expire le {{date}}.",
  "cancel": "Annuler",
  "error_toast": "Une erreur est survenue."
}
```

- [ ] **Créer `frontend/src/i18n/en/apikeys.json`**

```json
{
  "tab": "API Keys",
  "add_btn": "Create key",
  "empty": "No API keys. Create one to access this workspace.",
  "col_name": "Name",
  "col_fingerprint": "Fingerprint",
  "col_status": "Status",
  "col_created": "Created",
  "status_active": "Active",
  "status_grace_period": "Grace {{hours}}h",
  "status_revoked": "Revoked",
  "status_expired": "Expired",
  "rotate_btn": "Rotate",
  "revoke_btn": "Revoke",
  "revoke_confirm_title": "Revoke this key?",
  "revoke_confirm_body": "The key will be immediately invalid. Irreversible action.",
  "revoked_toast": "Key revoked.",
  "create_dialog_title": "Create API key",
  "field_name": "Name",
  "field_name_placeholder": "Production, CI/CD agent…",
  "create_save": "Create",
  "created_key_title": "Key created — copy it now",
  "created_key_warning": "This key will not be shown again. Copy it before closing.",
  "copy_btn": "Copy",
  "copied_toast": "Key copied.",
  "close": "Close",
  "rotate_dialog_title": "Key rotation",
  "rotate_confirm": "A new key will be generated. The old one stays valid for 72 hours.",
  "rotate_save": "Rotate key",
  "rotated_new_key_title": "New key — copy it now",
  "grace_info": "Old key expires on {{date}}.",
  "cancel": "Cancel",
  "error_toast": "An error occurred."
}
```

- [ ] **Enregistrer le namespace `apikeys` dans `i18n.ts`** en suivant le pattern existant (fr + en)

- [ ] **Ajouter `"apikeys": "API Keys"` dans `tabs` des fichiers workspace i18n** (fr + en)

- [ ] **Vérifier TypeScript + JSON**

```bash
cd frontend && npx tsc --noEmit
node -e "JSON.parse(require('fs').readFileSync('src/i18n/fr/apikeys.json','utf8')); console.log('OK')"
```

- [ ] **Commit**

```bash
git add frontend/src/lib/workspace-apikeys.types.ts \
        frontend/src/lib/workspace-apikeys.ts \
        frontend/src/hooks/useWorkspaceApiKeys.ts \
        frontend/src/i18n/fr/apikeys.json \
        frontend/src/i18n/en/apikeys.json \
        frontend/src/lib/i18n.ts \
        frontend/src/i18n/fr/workspace.json \
        frontend/src/i18n/en/workspace.json
git commit -m "feat(front): workspace api-keys types + API + hooks + i18n"
```

---

## Task 6 : Frontend — composants UI

**Files:**
- Create: `frontend/src/pages/workspace/CreateApiKeyDialog.tsx`
- Create: `frontend/src/pages/workspace/RotateApiKeyDialog.tsx`
- Create: `frontend/src/pages/workspace/WorkspaceApiKeysTab.tsx`
- Modify: `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx`

- [ ] **Créer `frontend/src/pages/workspace/CreateApiKeyDialog.tsx`**

```tsx
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Check } from "lucide-react";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateApiKey } from "@/hooks/useWorkspaceApiKeys";
import { useToast } from "@/hooks/useToast";
import type { ApiKeyCreated } from "@/lib/workspace-apikeys.types";

interface Props {
  workspaceName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateApiKeyDialog({ workspaceName, open, onOpenChange }: Props) {
  const { t } = useTranslation("apikeys");
  const { toast } = useToast();
  const mutation = useCreateApiKey(workspaceName);
  const [name, setName] = useState("");
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const [copied, setCopied] = useState(false);

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) { setName(""); setCreated(null); setCopied(false); }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      const result = await mutation.mutateAsync({ name: name.trim() });
      setCreated(result);
    } catch {
      toast({ title: t("error_toast"), variant: "destructive" });
    }
  }

  async function handleCopy() {
    if (!created) return;
    await navigator.clipboard.writeText(created.api_key);
    setCopied(true);
    toast({ title: t("copied_toast") });
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("create_dialog_title")}</DialogTitle>
        </DialogHeader>

        {!created ? (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("field_name")}
              </Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("field_name_placeholder")}
                className="mt-1"
                autoFocus
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => handleClose(false)}>
                {t("cancel")}
              </Button>
              <Button type="submit" disabled={!name.trim() || mutation.isPending}>
                {t("create_save")}
              </Button>
            </DialogFooter>
          </form>
        ) : (
          <div className="space-y-4">
            <div>
              <p className="text-sm font-semibold text-slate-900">{t("created_key_title")}</p>
              <p className="mt-1 text-xs text-amber-600">{t("created_key_warning")}</p>
            </div>
            <div className="flex items-center gap-2">
              <Input
                value={created.api_key}
                readOnly
                className="font-mono text-xs bg-slate-50"
              />
              <Button type="button" size="sm" onClick={handleCopy} className="shrink-0">
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </Button>
            </div>
            <DialogFooter>
              <Button onClick={() => handleClose(false)}>{t("close")}</Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Créer `frontend/src/pages/workspace/RotateApiKeyDialog.tsx`**

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Check } from "lucide-react";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useRotateApiKey } from "@/hooks/useWorkspaceApiKeys";
import { useToast } from "@/hooks/useToast";
import type { ApiKeyRotated } from "@/lib/workspace-apikeys.types";

interface Props {
  workspaceName: string;
  keyId: string;
  keyName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RotateApiKeyDialog({ workspaceName, keyId, keyName, open, onOpenChange }: Props) {
  const { t } = useTranslation("apikeys");
  const { toast } = useToast();
  const mutation = useRotateApiKey(workspaceName);
  const [rotated, setRotated] = useState<ApiKeyRotated | null>(null);
  const [copied, setCopied] = useState(false);

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) { setRotated(null); setCopied(false); }
  }

  async function handleRotate() {
    try {
      const result = await mutation.mutateAsync(keyId);
      setRotated(result);
    } catch {
      toast({ title: t("error_toast"), variant: "destructive" });
    }
  }

  async function handleCopy() {
    if (!rotated) return;
    await navigator.clipboard.writeText(rotated.new_api_key);
    setCopied(true);
    toast({ title: t("copied_toast") });
    setTimeout(() => setCopied(false), 2000);
  }

  const graceDate = rotated
    ? new Date(rotated.grace_until).toLocaleString("fr-FR")
    : "";

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("rotate_dialog_title")}</DialogTitle>
          {!rotated && (
            <DialogDescription>
              <strong>{keyName}</strong> — {t("rotate_confirm")}
            </DialogDescription>
          )}
        </DialogHeader>

        {!rotated ? (
          <DialogFooter>
            <Button variant="outline" onClick={() => handleClose(false)}>
              {t("cancel")}
            </Button>
            <Button onClick={handleRotate} disabled={mutation.isPending}>
              {t("rotate_save")}
            </Button>
          </DialogFooter>
        ) : (
          <div className="space-y-4">
            <p className="text-sm font-semibold text-slate-900">{t("rotated_new_key_title")}</p>
            <p className="text-xs text-amber-600">{t("created_key_warning")}</p>
            <div className="flex items-center gap-2">
              <Input
                value={rotated.new_api_key}
                readOnly
                className="font-mono text-xs bg-slate-50"
              />
              <Button type="button" size="sm" onClick={handleCopy} className="shrink-0">
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </Button>
            </div>
            <p className="text-xs text-slate-500">
              {t("grace_info", { date: graceDate })}
            </p>
            <DialogFooter>
              <Button onClick={() => handleClose(false)}>{t("close")}</Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Créer `frontend/src/pages/workspace/WorkspaceApiKeysTab.tsx`**

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { RotateCcw, XCircle } from "lucide-react";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useWorkspaceApiKeys, useRevokeApiKey } from "@/hooks/useWorkspaceApiKeys";
import { useToast } from "@/hooks/useToast";
import { CreateApiKeyDialog } from "./CreateApiKeyDialog";
import { RotateApiKeyDialog } from "./RotateApiKeyDialog";
import type { ApiKey } from "@/lib/workspace-apikeys.types";

const STATUS_COLORS: Record<string, string> = {
  active: "text-emerald-600",
  grace_period: "text-amber-500",
  revoked: "text-red-400",
  expired: "text-slate-400",
};

interface Props {
  workspaceName: string;
}

export function WorkspaceApiKeysTab({ workspaceName }: Props) {
  const { t } = useTranslation("apikeys");
  const { toast } = useToast();
  const { data: keys = [], isLoading } = useWorkspaceApiKeys(workspaceName);
  const revokeMutation = useRevokeApiKey(workspaceName);

  const [createOpen, setCreateOpen] = useState(false);
  const [toRotate, setToRotate] = useState<ApiKey | null>(null);
  const [toRevoke, setToRevoke] = useState<ApiKey | null>(null);

  async function handleRevoke() {
    if (!toRevoke) return;
    try {
      await revokeMutation.mutateAsync(toRevoke.id);
      toast({ title: t("revoked_toast") });
    } catch {
      toast({ title: t("error_toast"), variant: "destructive" });
    } finally {
      setToRevoke(null);
    }
  }

  function statusLabel(key: ApiKey) {
    if (key.status === "grace_period" && key.rotated_at) {
      const expires = new Date(key.rotated_at);
      expires.setHours(expires.getHours() + 72);
      const hoursLeft = Math.max(0, Math.round((expires.getTime() - Date.now()) / 3_600_000));
      return t("status_grace_period", { hours: hoursLeft });
    }
    return t(`status_${key.status}`);
  }

  return (
    <div className="space-y-4 pt-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          {t("add_btn")}
        </Button>
      </div>

      {!isLoading && keys.length === 0 ? (
        <div className="rounded border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("empty")}
        </div>
      ) : (
        <div className="overflow-hidden rounded border border-slate-200">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("col_name")}</TableHead>
                <TableHead>{t("col_fingerprint")}</TableHead>
                <TableHead>{t("col_status")}</TableHead>
                <TableHead>{t("col_created")}</TableHead>
                <TableHead className="w-28" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.map((k) => (
                <TableRow key={k.id} className={k.status === "revoked" || k.status === "expired" ? "opacity-50" : ""}>
                  <TableCell className="font-medium">{k.name}</TableCell>
                  <TableCell className="font-mono text-xs text-slate-500">
                    {k.fingerprint_preview}…
                  </TableCell>
                  <TableCell className={`text-xs font-medium ${STATUS_COLORS[k.status] ?? ""}`}>
                    {statusLabel(k)}
                  </TableCell>
                  <TableCell className="text-xs text-slate-400">
                    {new Date(k.created_at).toLocaleDateString("fr-FR")}
                  </TableCell>
                  <TableCell>
                    {(k.status === "active" || k.status === "grace_period") && (
                      <div className="flex items-center gap-1 justify-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setToRotate(k)}
                          aria-label={t("rotate_btn")}
                        >
                          <RotateCcw className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setToRevoke(k)}
                          className="text-rose-600 hover:text-rose-700"
                          aria-label={t("revoke_btn")}
                        >
                          <XCircle className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <CreateApiKeyDialog
        workspaceName={workspaceName}
        open={createOpen}
        onOpenChange={setCreateOpen}
      />

      {toRotate && (
        <RotateApiKeyDialog
          workspaceName={workspaceName}
          keyId={toRotate.id}
          keyName={toRotate.name}
          open={!!toRotate}
          onOpenChange={(o) => { if (!o) setToRotate(null); }}
        />
      )}

      <AlertDialog open={!!toRevoke} onOpenChange={(o) => { if (!o) setToRevoke(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("revoke_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>{t("revoke_confirm_body")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={handleRevoke} className="bg-rose-600 hover:bg-rose-700">
              {t("revoke_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
```

- [ ] **Modifier `WorkspaceDetailPanel.tsx`** — ajouter l'onglet API Keys

Ajouter l'import :
```tsx
import { WorkspaceApiKeysTab } from "./WorkspaceApiKeysTab";
```

Dans `<TabsList>`, après `"triggers"`, ajouter :
```tsx
<TabsTrigger value="apikeys">{t("tabs.apikeys")}</TabsTrigger>
```

Après le `</TabsContent>` triggers, ajouter :
```tsx
<TabsContent value="apikeys" className="pt-4">
  <WorkspaceApiKeysTab workspaceName={ws.name} />
</TabsContent>
```

- [ ] **Vérifier TypeScript + lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

- [ ] **Commit**

```bash
git add frontend/src/pages/workspace/WorkspaceApiKeysTab.tsx \
        frontend/src/pages/workspace/CreateApiKeyDialog.tsx \
        frontend/src/pages/workspace/RotateApiKeyDialog.tsx \
        frontend/src/pages/workspace/WorkspaceDetailPanel.tsx
git commit -m "feat(front): onglet API Keys — créer/rotation/révocation"
```
