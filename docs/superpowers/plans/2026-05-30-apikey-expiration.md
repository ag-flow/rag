# Validité des clés API (expires_at) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un champ de validité optionnel (nombre de jours) sur les clés `provider_api_keys` et `git_credentials`, stocké en DB comme date d'expiration absolue (`expires_at`).

**Architecture:** Migration ALTER TABLE sur les deux tables, `valid_days` en entrée des DTOs (le backend calcule `expires_at = now() + timedelta(days)`), `expires_at` en sortie et affiché dans les tables. Quatre dialogs mis à jour (Add + Replace × 2 modules). Aucun blocage ni alerte — stockage organisationnel uniquement.

**Tech Stack:** Python 3.12 / asyncpg / Pydantic v2 / pytest-asyncio — React 18 / TypeScript strict / i18next

---

## Structure des fichiers

### Backend (créer)
- `backend/migrations/027_add_expires_at.sql`

### Backend (modifier)
- `backend/src/rag/schemas/provider_api_keys.py`
- `backend/src/rag/schemas/git_credentials.py`
- `backend/src/rag/services/provider_api_keys.py`
- `backend/src/rag/services/git_credentials.py`
- `backend/tests/integration/test_services_provider_api_keys.py`
- `backend/tests/integration/test_services_git_credentials.py`

### Frontend (modifier)
- `frontend/src/lib/harpocrate-vaults.types.ts`
- `frontend/src/i18n/fr/harpocrate.json`
- `frontend/src/i18n/en/harpocrate.json`
- `frontend/src/pages/harpocrate/AddProviderKeyDialog.tsx`
- `frontend/src/pages/harpocrate/ReplaceProviderKeyDialog.tsx`
- `frontend/src/pages/harpocrate/AddGitKeyDialog.tsx`
- `frontend/src/pages/harpocrate/ReplaceGitKeyDialog.tsx`
- `frontend/src/pages/harpocrate/VaultApikeysTab.tsx`

---

## Task 1 : Migration 027

**Files:**
- Create: `backend/migrations/027_add_expires_at.sql`

- [ ] **Créer la migration**

```sql
-- backend/migrations/027_add_expires_at.sql
-- Migration 027 — validité des clés API (expires_at)

ALTER TABLE provider_api_keys ADD COLUMN expires_at TIMESTAMPTZ NULL;
ALTER TABLE git_credentials    ADD COLUMN expires_at TIMESTAMPTZ NULL;
```

- [ ] **Commit**

```bash
git add backend/migrations/027_add_expires_at.sql
git commit -m "feat(db): migration 027 — expires_at sur provider_api_keys + git_credentials"
```

---

## Task 2 : Schemas backend

**Files:**
- Modify: `backend/src/rag/schemas/provider_api_keys.py`
- Modify: `backend/src/rag/schemas/git_credentials.py`

- [ ] **Modifier `backend/src/rag/schemas/provider_api_keys.py`**

Contenu complet du fichier :

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
    valid_days: int | None = Field(default=None, ge=1)

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
    valid_days: int | None = Field(default=None, ge=1)


class ProviderApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key_id: str
    label: str
    provider: str
    harpo_path: str
    expires_at: datetime | None
    created_at: datetime
```

- [ ] **Modifier `backend/src/rag/schemas/git_credentials.py`**

Contenu complet du fichier :

```python
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
    valid_days: int | None = Field(default=None, ge=1)

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
    valid_days: int | None = Field(default=None, ge=1)


class GitCredentialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key_id: str
    label: str
    host: GitHost
    scope_url: str | None
    harpo_path: str
    expires_at: datetime | None
    created_at: datetime
```

- [ ] **Vérifier le lint**

```bash
cd backend && uv run ruff check src/rag/schemas/provider_api_keys.py src/rag/schemas/git_credentials.py
```

Résultat attendu : aucune erreur.

- [ ] **Commit**

```bash
git add backend/src/rag/schemas/provider_api_keys.py backend/src/rag/schemas/git_credentials.py
git commit -m "feat(schemas): valid_days + expires_at sur provider_api_keys + git_credentials"
```

---

## Task 3 : Service provider_api_keys (TDD)

**Files:**
- Modify: `backend/src/rag/services/provider_api_keys.py`
- Modify: `backend/tests/integration/test_services_provider_api_keys.py`

- [ ] **Ajouter les tests (rouge)**

Dans `backend/tests/integration/test_services_provider_api_keys.py`, ajouter ces imports en tête si absents :

```python
from datetime import UTC, datetime, timedelta
```

Ajouter ces trois tests à la fin du fichier :

```python
async def test_create_with_valid_days_sets_expires_at(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v6")
    svc = _mock_vault_svc()

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await create_provider_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=ProviderApiKeyCreate(
                    key_id="exp-key",
                    label="Expiring",
                    provider="openai",
                    value="sk-x",
                    valid_days=30,
                ),
            )

    assert created.expires_at is not None
    expected = datetime.now(UTC) + timedelta(days=30)
    assert abs((created.expires_at - expected).total_seconds()) < 5


async def test_create_without_valid_days_expires_at_is_none(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v7")
    svc = _mock_vault_svc()

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await create_provider_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=ProviderApiKeyCreate(
                    key_id="no-exp",
                    label="No expiry",
                    provider="openai",
                    value="sk-x",
                ),
            )

    assert created.expires_at is None


async def test_update_valid_days_recalculates_expires_at(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v8")
    svc = _mock_vault_svc()

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await create_provider_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=ProviderApiKeyCreate(
                    key_id="upd-exp",
                    label="L",
                    provider="openai",
                    value="sk-x",
                ),
            )

    assert created.expires_at is None

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            updated = await update_provider_key(
                conn,
                key_id=str(created.id),
                vault=vault,
                vault_svc=svc,
                req=ProviderApiKeyUpdate(valid_days=60),
            )

    assert updated is not None
    assert updated.expires_at is not None
    expected = datetime.now(UTC) + timedelta(days=60)
    assert abs((updated.expires_at - expected).total_seconds()) < 5
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/integration/test_services_provider_api_keys.py::test_create_with_valid_days_sets_expires_at -v 2>&1 | head -15
```

Résultat attendu : FAILED (colonne inconnue ou champ manquant).

- [ ] **Modifier `backend/src/rag/services/provider_api_keys.py`**

Ajouter l'import en tête (après les imports existants) :

```python
from datetime import UTC, datetime, timedelta
```

Remplacer `list_provider_keys` :

```python
async def list_provider_keys(
    conn: asyncpg.Connection,
    *,
    vault_id: str,
) -> list[ProviderApiKeyOut]:
    rows = await conn.fetch(
        "SELECT id, key_id, label, provider, harpo_path, expires_at, created_at "
        "FROM provider_api_keys WHERE vault_id = $1::uuid "
        "ORDER BY provider, key_id",
        vault_id,
    )
    return [ProviderApiKeyOut.model_validate(dict(r)) for r in rows]
```

Remplacer le bloc `try` dans `create_provider_key` (calcul de `expires_at` + INSERT) :

```python
    expires_at = (
        datetime.now(UTC) + timedelta(days=req.valid_days)
        if req.valid_days is not None
        else None
    )

    try:
        row = await conn.fetchrow(
            "INSERT INTO provider_api_keys "
            "(key_id, label, provider, vault_id, harpo_path, expires_at) "
            "VALUES ($1, $2, $3, $4::uuid, $5, $6) "
            "RETURNING id, key_id, label, provider, harpo_path, expires_at, created_at",
            req.key_id,
            req.label,
            req.provider,
            vault["id"],
            vault_ref,
            expires_at,
        )
```

Remplacer `update_provider_key` intégralement :

```python
async def update_provider_key(
    conn: asyncpg.Connection,
    *,
    key_id: str,
    vault: dict[str, Any],
    vault_svc: Any,
    req: ProviderApiKeyUpdate,
) -> ProviderApiKeyOut | None:
    row = await conn.fetchrow(
        "SELECT id, key_id, label, provider, harpo_path, expires_at, created_at "
        "FROM provider_api_keys WHERE id = $1::uuid AND vault_id = $2::uuid",
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
    new_expires_at = (
        datetime.now(UTC) + timedelta(days=req.valid_days)
        if req.valid_days is not None
        else row["expires_at"]
    )
    updated = await conn.fetchrow(
        "UPDATE provider_api_keys SET label = $1, expires_at = $2 WHERE id = $3::uuid "
        "RETURNING id, key_id, label, provider, harpo_path, expires_at, created_at",
        new_label,
        new_expires_at,
        key_id,
    )
    log.info("provider_key.updated", id=key_id)
    return ProviderApiKeyOut.model_validate(dict(updated))
```

- [ ] **Vérifier que tous les tests provider passent**

```bash
cd backend && uv run pytest tests/integration/test_services_provider_api_keys.py -v
```

Résultat attendu : 8 tests PASS (5 existants + 3 nouveaux).

- [ ] **Commit**

```bash
git add backend/src/rag/services/provider_api_keys.py \
        backend/tests/integration/test_services_provider_api_keys.py
git commit -m "feat(services): expires_at sur provider_api_keys"
```

---

## Task 4 : Service git_credentials (TDD)

**Files:**
- Modify: `backend/src/rag/services/git_credentials.py`
- Modify: `backend/tests/integration/test_services_git_credentials.py`

- [ ] **Ajouter les tests (rouge)**

Dans `backend/tests/integration/test_services_git_credentials.py`, ajouter ces imports en tête si absents :

```python
from datetime import UTC, datetime, timedelta
```

Ajouter ces trois tests à la fin du fichier :

```python
async def test_create_with_valid_days_sets_expires_at(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v6")
    svc = _mock_vault_svc()

    with patch("rag.services.git_credentials.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await create_git_credential(
                conn,
                vault=vault,
                vault_svc=svc,
                req=GitCredentialCreate(
                    key_id="exp-pat",
                    label="Expiring",
                    host="github",
                    value="ghp_x",
                    valid_days=90,
                ),
            )

    assert created.expires_at is not None
    expected = datetime.now(UTC) + timedelta(days=90)
    assert abs((created.expires_at - expected).total_seconds()) < 5


async def test_create_without_valid_days_expires_at_is_none(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v7")
    svc = _mock_vault_svc()

    with patch("rag.services.git_credentials.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await create_git_credential(
                conn,
                vault=vault,
                vault_svc=svc,
                req=GitCredentialCreate(
                    key_id="no-exp",
                    label="No expiry",
                    host="gitlab",
                    value="glpat_x",
                ),
            )

    assert created.expires_at is None


async def test_update_valid_days_recalculates_expires_at(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v8")
    svc = _mock_vault_svc()

    with patch("rag.services.git_credentials.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await create_git_credential(
                conn,
                vault=vault,
                vault_svc=svc,
                req=GitCredentialCreate(
                    key_id="upd-exp",
                    label="L",
                    host="github",
                    value="ghp_x",
                ),
            )

    assert created.expires_at is None

    with patch("rag.services.git_credentials.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            updated = await update_git_credential(
                conn,
                key_id=str(created.id),
                vault=vault,
                vault_svc=svc,
                req=GitCredentialUpdate(valid_days=30),
            )

    assert updated is not None
    assert updated.expires_at is not None
    expected = datetime.now(UTC) + timedelta(days=30)
    assert abs((updated.expires_at - expected).total_seconds()) < 5
```

- [ ] **Modifier `backend/src/rag/services/git_credentials.py`**

Ajouter l'import en tête :

```python
from datetime import UTC, datetime, timedelta
```

Remplacer `list_git_credentials` :

```python
async def list_git_credentials(
    conn: asyncpg.Connection,
    *,
    vault_id: str,
) -> list[GitCredentialOut]:
    rows = await conn.fetch(
        "SELECT id, key_id, label, host, scope_url, harpo_path, expires_at, created_at "
        "FROM git_credentials WHERE vault_id = $1::uuid "
        "ORDER BY host, key_id",
        vault_id,
    )
    return [GitCredentialOut.model_validate(dict(r)) for r in rows]
```

Remplacer le bloc `try` dans `create_git_credential` :

```python
    expires_at = (
        datetime.now(UTC) + timedelta(days=req.valid_days)
        if req.valid_days is not None
        else None
    )

    try:
        row = await conn.fetchrow(
            "INSERT INTO git_credentials "
            "(key_id, label, host, scope_url, vault_id, harpo_path, expires_at) "
            "VALUES ($1, $2, $3, $4, $5::uuid, $6, $7) "
            "RETURNING id, key_id, label, host, scope_url, harpo_path, expires_at, created_at",
            req.key_id,
            req.label,
            req.host,
            req.scope_url,
            vault["id"],
            vault_ref,
            expires_at,
        )
```

Remplacer `update_git_credential` intégralement :

```python
async def update_git_credential(
    conn: asyncpg.Connection,
    *,
    key_id: str,
    vault: dict[str, Any],
    vault_svc: Any,
    req: GitCredentialUpdate,
) -> GitCredentialOut | None:
    row = await conn.fetchrow(
        "SELECT id, key_id, label, host, scope_url, harpo_path, expires_at, created_at "
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
    new_expires_at = (
        datetime.now(UTC) + timedelta(days=req.valid_days)
        if req.valid_days is not None
        else row["expires_at"]
    )
    updated = await conn.fetchrow(
        "UPDATE git_credentials SET label = $1, scope_url = $2, expires_at = $3 "
        "WHERE id = $4::uuid "
        "RETURNING id, key_id, label, host, scope_url, harpo_path, expires_at, created_at",
        new_label,
        new_scope_url,
        new_expires_at,
        key_id,
    )
    log.info("git_credential.updated", id=key_id)
    return GitCredentialOut.model_validate(dict(updated))
```

- [ ] **Vérifier que tous les tests git passent**

```bash
cd backend && uv run pytest tests/integration/test_services_git_credentials.py -v
```

Résultat attendu : 8 tests PASS (5 existants + 3 nouveaux).

- [ ] **Commit**

```bash
git add backend/src/rag/services/git_credentials.py \
        backend/tests/integration/test_services_git_credentials.py
git commit -m "feat(services): expires_at sur git_credentials"
```

---

## Task 5 : Frontend — types + i18n

**Files:**
- Modify: `frontend/src/lib/harpocrate-vaults.types.ts`
- Modify: `frontend/src/i18n/fr/harpocrate.json`
- Modify: `frontend/src/i18n/en/harpocrate.json`

- [ ] **Mettre à jour `harpocrate-vaults.types.ts`**

Dans le type `ProviderApiKey`, ajouter `expires_at: string | null;`
Dans `ProviderApiKeyCreate`, ajouter `valid_days?: number | null;`
Dans `ProviderApiKeyUpdate`, ajouter `valid_days?: number | null;`
Dans le type `GitCredential`, ajouter `expires_at: string | null;`
Dans `GitCredentialCreate`, ajouter `valid_days?: number | null;`
Dans `GitCredentialUpdate`, ajouter `valid_days?: number | null;`

Résultat final des types concernés :

```typescript
export type ProviderApiKey = {
  id: string;
  key_id: string;
  label: string;
  provider: string;
  harpo_path: string;
  expires_at: string | null;
  created_at: string;
};

export type ProviderApiKeyCreate = {
  key_id: string;
  label: string;
  provider: string;
  value: string;
  valid_days?: number | null;
};

export type ProviderApiKeyUpdate = {
  label?: string;
  value?: string;
  valid_days?: number | null;
};

export type GitCredential = {
  id: string;
  key_id: string;
  label: string;
  host: GitHost;
  scope_url: string | null;
  harpo_path: string;
  expires_at: string | null;
  created_at: string;
};

export type GitCredentialCreate = {
  key_id: string;
  label: string;
  host: GitHost;
  scope_url?: string | null;
  value: string;
  valid_days?: number | null;
};

export type GitCredentialUpdate = {
  label?: string;
  scope_url?: string | null;
  value?: string;
  valid_days?: number | null;
};
```

- [ ] **Mettre à jour `frontend/src/i18n/fr/harpocrate.json`**

Dans le bloc `"apikeys"`, ajouter après `"col_label"` :

```json
"col_expires_at": "Expire le",
"field_valid_days": "Durée de validité (jours)",
"field_valid_days_help": "Laisser vide pour une clé non-expirable",
```

Dans le bloc `"gitkeys"`, ajouter après `"col_scope_url"` :

```json
"col_expires_at": "Expire le",
"field_valid_days": "Durée de validité (jours)",
"field_valid_days_help": "Laisser vide pour un token non-expirable",
```

- [ ] **Mettre à jour `frontend/src/i18n/en/harpocrate.json`**

Dans le bloc `"apikeys"`, ajouter après `"col_label"` :

```json
"col_expires_at": "Expires on",
"field_valid_days": "Validity (days)",
"field_valid_days_help": "Leave empty for a non-expiring key",
```

Dans le bloc `"gitkeys"`, ajouter après `"col_scope_url"` :

```json
"col_expires_at": "Expires on",
"field_valid_days": "Validity (days)",
"field_valid_days_help": "Leave empty for a non-expiring token",
```

- [ ] **Vérifier TypeScript + JSON valide**

```bash
cd frontend && npx tsc --noEmit
node -e "JSON.parse(require('fs').readFileSync('src/i18n/fr/harpocrate.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/en/harpocrate.json','utf8')); console.log('JSON OK')"
```

Résultat attendu : aucune erreur TS, `JSON OK`.

- [ ] **Commit**

```bash
git add frontend/src/lib/harpocrate-vaults.types.ts \
        frontend/src/i18n/fr/harpocrate.json \
        frontend/src/i18n/en/harpocrate.json
git commit -m "feat(front): types + i18n expires_at / valid_days"
```

---

## Task 6 : AddProviderKeyDialog + ReplaceProviderKeyDialog

**Files:**
- Modify: `frontend/src/pages/harpocrate/AddProviderKeyDialog.tsx`
- Modify: `frontend/src/pages/harpocrate/ReplaceProviderKeyDialog.tsx`

- [ ] **Modifier `AddProviderKeyDialog.tsx`**

Ajouter l'état `validDays` après les états existants :

```tsx
const [validDays, setValidDays] = useState("");
```

Dans `handleClose`, ajouter le reset :

```tsx
setValidDays("");
```

Dans `handleSubmit`, modifier `mutateAsync` :

```tsx
await mutation.mutateAsync({
  key_id: keyId,
  label,
  provider,
  value,
  valid_days: validDays ? parseInt(validDays, 10) : null,
});
```

Ajouter le champ dans le formulaire, après le champ `value` et avant `harpoPath` :

```tsx
<div>
  <Label className="text-xs uppercase tracking-wider text-slate-600">
    {t("apikeys.field_valid_days")}
  </Label>
  <Input
    type="number"
    min={1}
    step={1}
    value={validDays}
    onChange={(e) => setValidDays(e.target.value)}
    placeholder="90"
    className="mt-1"
  />
  <p className="mt-1 text-xs text-slate-400">{t("apikeys.field_valid_days_help")}</p>
</div>
```

- [ ] **Modifier `ReplaceProviderKeyDialog.tsx`**

Ajouter l'état `validDays` :

```tsx
const [validDays, setValidDays] = useState("");
```

Dans `handleClose`, ajouter le reset :

```tsx
setValidDays("");
```

Dans `handleSubmit`, modifier le payload :

```tsx
await mutation.mutateAsync({
  keyId,
  payload: {
    value: newValue,
    valid_days: validDays ? parseInt(validDays, 10) : null,
  },
});
```

Ajouter le champ dans le formulaire, après le champ `field_new_value` :

```tsx
<div>
  <Label className="text-xs uppercase tracking-wider text-slate-600">
    {t("apikeys.field_valid_days")}
  </Label>
  <Input
    type="number"
    min={1}
    step={1}
    value={validDays}
    onChange={(e) => setValidDays(e.target.value)}
    placeholder="90"
    className="mt-1"
  />
  <p className="mt-1 text-xs text-slate-400">{t("apikeys.field_valid_days_help")}</p>
</div>
```

- [ ] **Vérifier TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

Résultat attendu : aucune erreur.

- [ ] **Commit**

```bash
git add frontend/src/pages/harpocrate/AddProviderKeyDialog.tsx \
        frontend/src/pages/harpocrate/ReplaceProviderKeyDialog.tsx
git commit -m "feat(front): valid_days dans AddProviderKeyDialog + ReplaceProviderKeyDialog"
```

---

## Task 7 : AddGitKeyDialog + ReplaceGitKeyDialog

**Files:**
- Modify: `frontend/src/pages/harpocrate/AddGitKeyDialog.tsx`
- Modify: `frontend/src/pages/harpocrate/ReplaceGitKeyDialog.tsx`

- [ ] **Modifier `AddGitKeyDialog.tsx`**

Ajouter l'état `validDays` après les états existants :

```tsx
const [validDays, setValidDays] = useState("");
```

Dans `handleClose`, ajouter le reset :

```tsx
setValidDays("");
```

Dans `handleSubmit`, modifier `mutateAsync` :

```tsx
await mutation.mutateAsync({
  key_id: keyId,
  label,
  host,
  scope_url: scopeUrl.trim() || null,
  value,
  valid_days: validDays ? parseInt(validDays, 10) : null,
});
```

Ajouter le champ dans le formulaire, après le champ `field_value` et avant `harpoPath` :

```tsx
<div>
  <Label className="text-xs uppercase tracking-wider text-slate-600">
    {t("gitkeys.field_valid_days")}
  </Label>
  <Input
    type="number"
    min={1}
    step={1}
    value={validDays}
    onChange={(e) => setValidDays(e.target.value)}
    placeholder="90"
    className="mt-1"
  />
  <p className="mt-1 text-xs text-slate-400">{t("gitkeys.field_valid_days_help")}</p>
</div>
```

- [ ] **Modifier `ReplaceGitKeyDialog.tsx`**

Ajouter l'état `validDays` :

```tsx
const [validDays, setValidDays] = useState("");
```

Dans `handleClose`, ajouter le reset :

```tsx
setValidDays("");
```

Dans `handleSubmit`, modifier le payload :

```tsx
await mutation.mutateAsync({
  keyId,
  payload: {
    value: newValue,
    valid_days: validDays ? parseInt(validDays, 10) : null,
  },
});
```

Ajouter le champ dans le formulaire, après le champ `field_new_value` :

```tsx
<div>
  <Label className="text-xs uppercase tracking-wider text-slate-600">
    {t("gitkeys.field_valid_days")}
  </Label>
  <Input
    type="number"
    min={1}
    step={1}
    value={validDays}
    onChange={(e) => setValidDays(e.target.value)}
    placeholder="90"
    className="mt-1"
  />
  <p className="mt-1 text-xs text-slate-400">{t("gitkeys.field_valid_days_help")}</p>
</div>
```

- [ ] **Vérifier TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

Résultat attendu : aucune erreur.

- [ ] **Commit**

```bash
git add frontend/src/pages/harpocrate/AddGitKeyDialog.tsx \
        frontend/src/pages/harpocrate/ReplaceGitKeyDialog.tsx
git commit -m "feat(front): valid_days dans AddGitKeyDialog + ReplaceGitKeyDialog"
```

---

## Task 8 : VaultApikeysTab — colonne expires_at

**Files:**
- Modify: `frontend/src/pages/harpocrate/VaultApikeysTab.tsx`

- [ ] **Ajouter la colonne `expires_at` dans la section provider**

Dans le `<TableHeader>` provider, ajouter après `<TableHead>{t("apikeys.col_label")}</TableHead>` :

```tsx
<TableHead>{t("apikeys.col_expires_at")}</TableHead>
```

Dans chaque `<TableRow>` provider (body), ajouter après la cellule label :

```tsx
<TableCell className="text-xs text-slate-500">
  {k.expires_at
    ? new Date(k.expires_at).toLocaleDateString("fr-FR", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })
    : "—"}
</TableCell>
```

- [ ] **Ajouter la colonne `expires_at` dans la section git**

Dans le `<TableHeader>` git, ajouter après `<TableHead>{t("gitkeys.col_scope_url")}</TableHead>` :

```tsx
<TableHead>{t("gitkeys.col_expires_at")}</TableHead>
```

Dans chaque `<TableRow>` git (body), ajouter après la cellule scope_url :

```tsx
<TableCell className="text-xs text-slate-500">
  {k.expires_at
    ? new Date(k.expires_at).toLocaleDateString("fr-FR", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })
    : "—"}
</TableCell>
```

- [ ] **Vérifier TypeScript + lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Résultat attendu : aucune erreur.

- [ ] **Commit**

```bash
git add frontend/src/pages/harpocrate/VaultApikeysTab.tsx
git commit -m "feat(front): colonne expires_at dans VaultApikeysTab"
```
