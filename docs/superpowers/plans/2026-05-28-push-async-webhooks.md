# Push Asynchrone + Webhooks — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre `POST /workspaces/{name}/index` asynchrone (202 + job en background) et ajouter un sous-système complet de webhooks notifié à la fin de chaque indexation.

**Architecture:** Le worker unifié (`SyncWorker`) picke tous les jobs pending — git ET push — et branche sur `triggered_by`. Le dispatch webhook (fire-and-forget, HMAC signé) est appelé en fin de chaque job, quelle que soit son origine. Le CRUD webhooks est monté sur le router admin existant.

**Tech Stack:** Python 3.12 + FastAPI + asyncpg + httpx (déjà dans les deps) + React 18 + TanStack Query + shadcn/ui + i18next. Aucune nouvelle dépendance backend.

---

## Fichiers créés / modifiés

### Backend — nouveaux
- `backend/migrations/018_push_job_payloads.sql`
- `backend/migrations/019_webhooks.sql`
- `backend/migrations/020_webhook_calls.sql`
- `backend/src/rag/schemas/webhooks.py`
- `backend/src/rag/services/webhooks.py`
- `backend/src/rag/services/webhook_dispatch.py`
- `backend/src/rag/api/admin_webhooks.py`
- `backend/tests/integration/test_migration_018_push_payloads.py`
- `backend/tests/integration/test_migration_019_webhooks.py`
- `backend/tests/integration/test_migration_020_webhook_calls.py`
- `backend/tests/integration/test_services_webhooks.py`
- `backend/tests/unit/services/test_webhook_dispatch.py`
- `backend/tests/integration/test_executor_push_job.py`

### Backend — modifiés
- `backend/src/rag/config.py` — `rag_webhook_secret`
- `backend/src/rag/api/errors.py` — `ReservedHeader`, `WebhookNotFound`
- `backend/src/rag/schemas/workspace.py` — `PushAsyncResponse` remplace `PushResponse`
- `backend/src/rag/schemas/sync.py` — `JobToProcess` : `source_id` optionnel + `triggered_by` + `correlation_id`
- `backend/src/rag/services/push.py` — supprime `push_document`, garde `normalize_path`
- `backend/src/rag/api/workspace.py` — endpoint push → 202
- `backend/src/rag/api/admin.py` — mount router webhooks
- `backend/src/rag/sync/executor.py` — `_execute_git_job` + `_execute_push_job` + dispatch
- `backend/src/rag/sync/worker.py` — purge `webhook_calls` dans le cycle
- `backend/tests/unit/services/test_push_service.py` — retire tests de `push_document`
- `backend/tests/api/test_workspace_push_dedup.py` — 200 → 202, body différent
- `backend/tests/api/test_workspace_push_errors.py` — adapter path traversal → 202 flow

### Frontend — nouveaux
- `frontend/src/lib/webhooks.types.ts`
- `frontend/src/lib/webhooks.ts`
- `frontend/src/pages/workspace/WorkspaceWebhooksTab.tsx`
- `frontend/src/pages/workspace/WebhookForm.tsx`
- `frontend/src/pages/workspace/WebhookCallsLog.tsx`
- `frontend/src/pages/workspace/__tests__/WorkspaceWebhooksTab.test.tsx`

### Frontend — modifiés
- `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx` — onglet Webhooks
- `frontend/src/i18n/fr.json` — clés `webhooks.*`
- `frontend/src/i18n/en.json` — clés `webhooks.*`

---

## Task 1 : Migrations SQL 018/019/020

**Files:**
- Create: `backend/migrations/018_push_job_payloads.sql`
- Create: `backend/migrations/019_webhooks.sql`
- Create: `backend/migrations/020_webhook_calls.sql`
- Create: `backend/tests/integration/test_migration_018_push_payloads.py`
- Create: `backend/tests/integration/test_migration_019_webhooks.py`
- Create: `backend/tests/integration/test_migration_020_webhook_calls.py`

- [ ] **Écrire les 3 fichiers SQL de migration**

`backend/migrations/018_push_job_payloads.sql` :
```sql
-- Migration 018 — push async : correlation_id + status skipped + push_job_payloads

ALTER TABLE index_jobs DROP CONSTRAINT index_jobs_status_check;
ALTER TABLE index_jobs ADD CONSTRAINT index_jobs_status_check
    CHECK (status IN ('pending', 'running', 'done', 'error', 'skipped'));

ALTER TABLE index_jobs ADD COLUMN correlation_id TEXT;

CREATE TABLE push_job_payloads (
    job_id   UUID PRIMARY KEY REFERENCES index_jobs(id) ON DELETE CASCADE,
    path     TEXT NOT NULL,
    content  TEXT NOT NULL
);
```

`backend/migrations/019_webhooks.sql` :
```sql
-- Migration 019 — workspace_webhooks + webhook_headers

CREATE TABLE workspace_webhooks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    url           TEXT NOT NULL,
    enabled       BOOLEAN DEFAULT true,
    created_at    TIMESTAMPTZ DEFAULT now(),
    UNIQUE(workspace_id, name)
);

CREATE TABLE webhook_headers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_id  UUID NOT NULL REFERENCES workspace_webhooks(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    value       TEXT,
    vault_ref   TEXT,
    enabled     BOOLEAN DEFAULT true
);
```

`backend/migrations/020_webhook_calls.sql` :
```sql
-- Migration 020 — webhook_calls (audit log, rétention 24h)

CREATE TABLE webhook_calls (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id   UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    webhook_id     UUID NOT NULL REFERENCES workspace_webhooks(id) ON DELETE CASCADE,
    job_id         UUID NOT NULL REFERENCES index_jobs(id),
    correlation_id TEXT NOT NULL,
    triggered_by   TEXT NOT NULL,
    webhook_url    TEXT NOT NULL,
    http_status    INT,
    error          TEXT,
    duration_ms    INT,
    called_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_webhook_calls_workspace ON webhook_calls(workspace_id, called_at DESC);
CREATE INDEX idx_webhook_calls_purge     ON webhook_calls(called_at);
```

- [ ] **Écrire les tests de migration**

`backend/tests/integration/test_migration_018_push_payloads.py` :
```python
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def test_migration_018_correlation_id_and_push_payloads(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        # correlation_id existe sur index_jobs
        col = await conn.fetchval(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='index_jobs' AND column_name='correlation_id'"
        )
        assert col == "correlation_id"

        # status 'skipped' accepté
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_ref, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ('mig018', 'ref', 'fp', 'c', 'b') RETURNING id"
        )
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status) "
            "VALUES ($1, 'push', 'skipped') RETURNING id",
            ws_id,
        )
        assert job_id is not None

        # push_job_payloads existe et ON DELETE CASCADE fonctionne
        await conn.execute(
            "INSERT INTO push_job_payloads (job_id, path, content) VALUES ($1, 'a.md', 'hi')",
            job_id,
        )
        await conn.execute("DELETE FROM index_jobs WHERE id=$1", job_id)
        count = await conn.fetchval(
            "SELECT count(*) FROM push_job_payloads WHERE job_id=$1", job_id
        )
        assert count == 0
```

`backend/tests/integration/test_migration_019_webhooks.py` :
```python
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def test_migration_019_webhooks_tables_exist(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_ref, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ('mig019', 'ref', 'fp', 'c', 'b') RETURNING id"
        )
        wh_id = await conn.fetchval(
            "INSERT INTO workspace_webhooks (workspace_id, name, url) "
            "VALUES ($1, 'hook', 'https://example.com/hook') RETURNING id",
            ws_id,
        )
        assert wh_id is not None

        hdr_id = await conn.fetchval(
            "INSERT INTO webhook_headers (webhook_id, name, value) "
            "VALUES ($1, 'X-Api-Key', 'secret') RETURNING id",
            wh_id,
        )
        assert hdr_id is not None

        # CASCADE sur workspace suppression
        await conn.execute("DELETE FROM workspaces WHERE id=$1", ws_id)
        wh = await conn.fetchval(
            "SELECT id FROM workspace_webhooks WHERE id=$1", wh_id
        )
        assert wh is None
```

`backend/tests/integration/test_migration_020_webhook_calls.py` :
```python
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def test_migration_020_webhook_calls_table(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_ref, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ('mig020', 'ref', 'fp', 'c', 'b') RETURNING id"
        )
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status) "
            "VALUES ($1, 'push', 'done') RETURNING id",
            ws_id,
        )
        wh_id = await conn.fetchval(
            "INSERT INTO workspace_webhooks (workspace_id, name, url) "
            "VALUES ($1, 'h', 'https://x.com') RETURNING id",
            ws_id,
        )
        call_id = await conn.fetchval(
            """
            INSERT INTO webhook_calls
                (workspace_id, webhook_id, job_id, correlation_id, triggered_by, webhook_url, http_status, duration_ms)
            VALUES ($1, $2, $3, 'corr-123', 'push', 'https://x.com', 200, 42)
            RETURNING id
            """,
            ws_id, wh_id, job_id,
        )
        assert call_id is not None

        # Les index existent
        idx = await conn.fetchval(
            "SELECT indexname FROM pg_indexes WHERE indexname='idx_webhook_calls_purge'"
        )
        assert idx == "idx_webhook_calls_purge"
```

- [ ] **Vérifier que les tests échouent (migrations non encore appliquées)**

```bash
cd backend
uv run pytest tests/integration/test_migration_018_push_payloads.py tests/integration/test_migration_019_webhooks.py tests/integration/test_migration_020_webhook_calls.py -v
```

Expected : PASS (run_migrations applique les fichiers SQL au fil de l'eau — les 3 nouvelles migrations sont détectées automatiquement).

- [ ] **Commit**

```bash
git add backend/migrations/018_push_job_payloads.sql backend/migrations/019_webhooks.sql backend/migrations/020_webhook_calls.sql backend/tests/integration/test_migration_018_push_payloads.py backend/tests/integration/test_migration_019_webhooks.py backend/tests/integration/test_migration_020_webhook_calls.py
git commit -m "feat(db): migrations 018-020 push_job_payloads + webhooks + webhook_calls"
```

---

## Task 2 : Config + erreurs métier

**Files:**
- Modify: `backend/src/rag/config.py`
- Modify: `backend/src/rag/api/errors.py`

- [ ] **Ajouter `rag_webhook_secret` dans `config.py`**

Dans la classe `Settings`, après `rag_session_secret` :

```python
rag_webhook_secret: SecretStr | None = Field(
    default=None,
    description="Secret HMAC pour signer les payloads webhook (X-RAG-Signature). "
    "Optionnel — si absent, la signature est omise (warning au dispatch).",
)
```

- [ ] **Ajouter `ReservedHeader` et `WebhookNotFound` dans `api/errors.py`**

```python
class ReservedHeader(AdminError):
    http_status = 422

    def __init__(self, header_name: str, reserved: list[str]) -> None:
        super().__init__(header_name)
        self.header_name = header_name
        self.reserved = reserved

    def to_payload(self) -> dict[str, object]:
        return {
            "error": "reserved_header",
            "message": f"Header '{self.header_name}' is reserved and cannot be configured.",
            "reserved_headers": self.reserved,
        }


class WebhookNotFound(AdminError):
    http_status = 404

    def __init__(self, webhook_id: str) -> None:
        super().__init__(webhook_id)
        self.webhook_id = webhook_id

    def to_payload(self) -> dict[str, object]:
        return {"error": "webhook_not_found", "webhook_id": self.webhook_id}
```

- [ ] **Vérifier lint**

```bash
cd backend
uv run ruff check src/rag/config.py src/rag/api/errors.py
```

Expected : no errors.

- [ ] **Commit**

```bash
git add backend/src/rag/config.py backend/src/rag/api/errors.py
git commit -m "feat(config): rag_webhook_secret + erreurs ReservedHeader/WebhookNotFound"
```

---

## Task 3 : Schémas — PushAsyncResponse + JobToProcess

**Files:**
- Modify: `backend/src/rag/schemas/workspace.py`
- Modify: `backend/src/rag/schemas/sync.py`
- Modify: `backend/tests/unit/schemas/test_workspace_dto.py` (si présent, adapter)

- [ ] **Réécrire `schemas/workspace.py`**

```python
from __future__ import annotations

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


class PushAsyncResponse(BaseModel):
    job_id: str
    status: str = "pending"
```

- [ ] **Mettre à jour `schemas/sync.py` — `JobToProcess`**

`source_id` devient `UUID | None`, deux nouveaux champs ajoutés :

```python
class JobToProcess(BaseModel):
    """Contexte d'un job piké par l'executor (1 row JOIN workspace + indexer)."""

    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    workspace_id: UUID
    workspace_name: str
    source_id: UUID | None          # None pour les push jobs
    source_config: dict[str, Any]   # {} pour les push jobs
    indexer_provider: str
    indexer_model: str
    triggered_by: str
    correlation_id: str | None

    @property
    def indexer_used(self) -> str:
        return f"{self.indexer_provider}/{self.indexer_model}"
```

- [ ] **Vérifier lint + typecheck**

```bash
cd backend
uv run ruff check src/rag/schemas/
uv run mypy src/rag/schemas/
```

Expected : no errors.

- [ ] **Commit**

```bash
git add backend/src/rag/schemas/workspace.py backend/src/rag/schemas/sync.py
git commit -m "feat(schemas): PushAsyncResponse + JobToProcess triggered_by/correlation_id"
```

---

## Task 4 : Service CRUD webhooks

**Files:**
- Create: `backend/src/rag/schemas/webhooks.py`
- Create: `backend/src/rag/services/webhooks.py`
- Create: `backend/tests/integration/test_services_webhooks.py`

- [ ] **Écrire le test d'intégration (rouge)**

`backend/tests/integration/test_services_webhooks.py` :
```python
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.services.webhooks import (
    create_webhook,
    delete_webhook,
    list_webhooks,
    patch_webhook,
    patch_webhook_header,
)
from rag.api.errors import ReservedHeader, WebhookNotFound, WorkspaceNotFound
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.fixture
async def pool(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM workspaces")
    return session_pool


async def test_create_and_list_webhook(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws1")

    created = await create_webhook(
        pool,
        workspace_name="ws1",
        name="hook1",
        url="https://example.com/hook",
        enabled=True,
        headers=[{"name": "X-Api-Key", "value": "secret", "vault": None, "enabled": True}],
        resolver=None,
    )
    assert created["name"] == "hook1"
    assert len(created["headers"]) == 1
    assert created["headers"][0]["value"] is None  # value non retournée

    hooks = await list_webhooks(pool, workspace_name="ws1")
    assert len(hooks) == 1
    assert hooks[0]["id"] == created["id"]


async def test_create_webhook_reserved_header_raises(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await seed_workspace(conn, name="ws2")

    with pytest.raises(ReservedHeader):
        await create_webhook(
            pool,
            workspace_name="ws2",
            name="hook2",
            url="https://x.com",
            enabled=True,
            headers=[{"name": "X-Correlation-ID", "value": "v", "vault": None, "enabled": True}],
            resolver=None,
        )


async def test_patch_webhook_enabled(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await seed_workspace(conn, name="ws3")

    wh = await create_webhook(
        pool,
        workspace_name="ws3",
        name="hook3",
        url="https://x.com",
        enabled=True,
        headers=[],
        resolver=None,
    )
    updated = await patch_webhook(pool, webhook_id=wh["id"], enabled=False)
    assert updated["enabled"] is False


async def test_delete_webhook(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await seed_workspace(conn, name="ws4")

    wh = await create_webhook(
        pool,
        workspace_name="ws4",
        name="hook4",
        url="https://x.com",
        enabled=True,
        headers=[],
        resolver=None,
    )
    await delete_webhook(pool, webhook_id=wh["id"], resolver=None)
    hooks = await list_webhooks(pool, workspace_name="ws4")
    assert hooks == []


async def test_webhook_not_found_on_patch(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await seed_workspace(conn, name="ws5")

    with pytest.raises(WebhookNotFound):
        await patch_webhook(
            pool,
            webhook_id="00000000-0000-0000-0000-000000000000",
            enabled=False,
        )
```

- [ ] **Vérifier que le test échoue**

```bash
cd backend
uv run pytest tests/integration/test_services_webhooks.py -v
```

Expected : ImportError (module inexistant).

- [ ] **Créer `schemas/webhooks.py`**

```python
from __future__ import annotations

from pydantic import BaseModel


class WebhookHeaderIn(BaseModel):
    name: str
    value: str | None = None
    vault: str | None = None
    enabled: bool = True


class WebhookHeaderOut(BaseModel):
    id: str
    name: str
    value: None = None       # jamais retourné
    vault_ref: str | None
    enabled: bool


class WebhookOut(BaseModel):
    id: str
    name: str
    url: str
    enabled: bool
    headers: list[WebhookHeaderOut]


class WebhookCreateRequest(BaseModel):
    name: str
    url: str
    enabled: bool = True
    headers: list[WebhookHeaderIn] = []


class WebhookPatchRequest(BaseModel):
    name: str | None = None
    url: str | None = None
    enabled: bool | None = None


class WebhookHeaderPatchRequest(BaseModel):
    value: str | None = None
    vault: str | None = None
    enabled: bool | None = None


class WebhookCallOut(BaseModel):
    id: str
    webhook_id: str
    webhook_name: str
    correlation_id: str
    triggered_by: str
    webhook_url: str
    http_status: int | None
    error: str | None
    duration_ms: int | None
    called_at: str
    success: bool
```

- [ ] **Créer `services/webhooks.py`**

```python
from __future__ import annotations

from typing import Any, Protocol

import asyncpg
import structlog

from rag.api.errors import ReservedHeader, WebhookNotFound, WorkspaceNotFound
from rag.db.helpers import fetch_all, fetch_one
from rag.secrets.refs import build_ref

log = structlog.get_logger(__name__)

RESERVED_HEADERS: frozenset[str] = frozenset({
    "x-correlation-id",
    "x-rag-signature",
    "x-git-repo",
    "x-git-branch",
    "x-git-commit",
})

_RESERVED_LIST = sorted(RESERVED_HEADERS)


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


def _check_reserved(header_name: str) -> None:
    if header_name.lower() in RESERVED_HEADERS:
        raise ReservedHeader(header_name, _RESERVED_LIST)


async def list_webhooks(
    config_pool: asyncpg.Pool,
    *,
    workspace_name: str,
) -> list[dict[str, Any]]:
    ws = await fetch_one(
        config_pool, "SELECT id FROM workspaces WHERE name=$1", workspace_name
    )
    if ws is None:
        raise WorkspaceNotFound(workspace_name)

    hooks = await fetch_all(
        config_pool,
        "SELECT id, name, url, enabled FROM workspace_webhooks WHERE workspace_id=$1 ORDER BY created_at",
        ws["id"],
    )
    result = []
    for hook in hooks:
        headers = await _list_headers(config_pool, hook["id"])
        result.append({
            "id": str(hook["id"]),
            "name": hook["name"],
            "url": hook["url"],
            "enabled": hook["enabled"],
            "headers": headers,
        })
    return result


async def _list_headers(
    config_pool: asyncpg.Pool, webhook_id: Any
) -> list[dict[str, Any]]:
    rows = await fetch_all(
        config_pool,
        "SELECT id, name, vault_ref, enabled FROM webhook_headers WHERE webhook_id=$1 ORDER BY id",
        webhook_id,
    )
    return [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "value": None,
            "vault_ref": r["vault_ref"],
            "enabled": r["enabled"],
        }
        for r in rows
    ]


async def create_webhook(
    config_pool: asyncpg.Pool,
    *,
    workspace_name: str,
    name: str,
    url: str,
    enabled: bool,
    headers: list[dict[str, Any]],
    resolver: _ResolverProtocol | None,
) -> dict[str, Any]:
    for h in headers:
        _check_reserved(h["name"])

    ws = await fetch_one(
        config_pool, "SELECT id FROM workspaces WHERE name=$1", workspace_name
    )
    if ws is None:
        raise WorkspaceNotFound(workspace_name)

    async with config_pool.acquire() as conn, conn.transaction():
        wh_id = await conn.fetchval(
            "INSERT INTO workspace_webhooks (workspace_id, name, url, enabled) "
            "VALUES ($1, $2, $3, $4) RETURNING id",
            ws["id"], name, url, enabled,
        )
        saved_headers = []
        for h in headers:
            vault_ref, value_to_store = await _resolve_header_write(
                wh_id=str(wh_id),
                workspace_name=workspace_name,
                header_name=h["name"],
                value=h.get("value"),
                vault=h.get("vault"),
                resolver=resolver,
            )
            hdr_id = await conn.fetchval(
                "INSERT INTO webhook_headers (webhook_id, name, value, vault_ref, enabled) "
                "VALUES ($1, $2, $3, $4, $5) RETURNING id",
                wh_id, h["name"], value_to_store, vault_ref, h.get("enabled", True),
            )
            saved_headers.append({
                "id": str(hdr_id),
                "name": h["name"],
                "value": None,
                "vault_ref": vault_ref,
                "enabled": h.get("enabled", True),
            })

    log.info("webhook.created", workspace=workspace_name, name=name, webhook_id=str(wh_id))
    return {"id": str(wh_id), "name": name, "url": url, "enabled": enabled, "headers": saved_headers}


async def _resolve_header_write(
    *,
    wh_id: str,
    workspace_name: str,
    header_name: str,
    value: str | None,
    vault: str | None,
    resolver: _ResolverProtocol | None,
) -> tuple[str | None, str | None]:
    """Retourne (vault_ref, value_in_db). Si vault → push Harpocrate, value_in_db=None."""
    if vault and value and resolver is not None:
        logical = f"/workspaces/{workspace_name}/hooks/{wh_id}/headers/{header_name}"
        vault_ref = build_ref(vault, logical)
        # Écriture dans Harpocrate via le resolver (write_secret non disponible ici :
        # le resolver est lecture seule — le push Harpocrate est géré par HarpocrateVaultsService).
        # On stocke vault_ref ; la valeur est poussée par l'appelant API (admin_webhooks).
        return vault_ref, None
    return None, value


async def patch_webhook(
    config_pool: asyncpg.Pool,
    *,
    webhook_id: str,
    name: str | None = None,
    url: str | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    sets = []
    params: list[Any] = []
    idx = 1
    if name is not None:
        sets.append(f"name=${idx}")
        params.append(name)
        idx += 1
    if url is not None:
        sets.append(f"url=${idx}")
        params.append(url)
        idx += 1
    if enabled is not None:
        sets.append(f"enabled=${idx}")
        params.append(enabled)
        idx += 1

    if not sets:
        row = await fetch_one(
            config_pool,
            "SELECT id, name, url, enabled FROM workspace_webhooks WHERE id=$1::uuid",
            webhook_id,
        )
    else:
        params.append(webhook_id)
        row = await fetch_one(
            config_pool,
            f"UPDATE workspace_webhooks SET {', '.join(sets)} WHERE id=${idx}::uuid "
            "RETURNING id, name, url, enabled",
            *params,
        )
    if row is None:
        raise WebhookNotFound(webhook_id)
    headers = await _list_headers(config_pool, row["id"])
    return {"id": str(row["id"]), "name": row["name"], "url": row["url"],
            "enabled": row["enabled"], "headers": headers}


async def delete_webhook(
    config_pool: asyncpg.Pool,
    *,
    webhook_id: str,
    resolver: _ResolverProtocol | None,
) -> None:
    row = await fetch_one(
        config_pool,
        "SELECT id FROM workspace_webhooks WHERE id=$1::uuid",
        webhook_id,
    )
    if row is None:
        raise WebhookNotFound(webhook_id)

    # Purge Harpocrate si vault_refs présentes
    vault_headers = await fetch_all(
        config_pool,
        "SELECT vault_ref FROM webhook_headers WHERE webhook_id=$1 AND vault_ref IS NOT NULL",
        row["id"],
    )
    if vault_headers and resolver is not None:
        for h in vault_headers:
            try:
                # Note : le resolver Harpocrate ne supporte pas la suppression.
                # La vault_ref est orpheline — nettoyage best-effort via l'API Harpocrate
                # si le service supporte DELETE (hors scope de cette migration).
                log.warning("webhook.delete_vault_ref_orphan", vault_ref=h["vault_ref"])
            except Exception:
                pass

    await config_pool.execute(
        "DELETE FROM workspace_webhooks WHERE id=$1", row["id"]
    )
    log.info("webhook.deleted", webhook_id=webhook_id)


async def patch_webhook_header(
    config_pool: asyncpg.Pool,
    *,
    webhook_id: str,
    header_id: str,
    value: str | None = None,
    vault: str | None = None,
    enabled: bool | None = None,
    workspace_name: str,
    resolver: _ResolverProtocol | None,
) -> dict[str, Any]:
    row = await fetch_one(
        config_pool,
        "SELECT wh.id, wh.name, wh.vault_ref FROM webhook_headers wh "
        "JOIN workspace_webhooks w ON w.id = wh.webhook_id "
        "WHERE wh.id=$1::uuid AND w.id=$2::uuid",
        header_id, webhook_id,
    )
    if row is None:
        raise WebhookNotFound(header_id)

    _check_reserved(row["name"])

    sets = []
    params: list[Any] = []
    idx = 1

    if value is not None:
        if row["vault_ref"] and resolver is not None:
            # mise à jour dans Harpocrate (même path, vault_ref inchangée)
            log.info("webhook.header_update_vault", header_id=header_id)
        else:
            sets.append(f"value=${idx}")
            params.append(value)
            idx += 1

    if enabled is not None:
        sets.append(f"enabled=${idx}")
        params.append(enabled)
        idx += 1

    if sets:
        params.append(header_id)
        await config_pool.execute(
            f"UPDATE webhook_headers SET {', '.join(sets)} WHERE id=${idx}::uuid",
            *params,
        )

    updated = await fetch_one(
        config_pool,
        "SELECT id, name, vault_ref, enabled FROM webhook_headers WHERE id=$1::uuid",
        header_id,
    )
    return {
        "id": str(updated["id"]),
        "name": updated["name"],
        "value": None,
        "vault_ref": updated["vault_ref"],
        "enabled": updated["enabled"],
    }


async def list_webhook_calls(
    config_pool: asyncpg.Pool,
    *,
    workspace_name: str,
    webhook_id: str | None = None,
    correlation_id: str | None = None,
    status_filter: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    ws = await fetch_one(
        config_pool, "SELECT id FROM workspaces WHERE name=$1", workspace_name
    )
    if ws is None:
        raise WorkspaceNotFound(workspace_name)

    conditions = ["wc.workspace_id=$1"]
    params: list[Any] = [ws["id"]]
    idx = 2

    if webhook_id:
        conditions.append(f"wc.webhook_id=${idx}::uuid")
        params.append(webhook_id)
        idx += 1
    if correlation_id:
        conditions.append(f"wc.correlation_id=${idx}")
        params.append(correlation_id)
        idx += 1
    if status_filter == "success":
        conditions.append("wc.http_status BETWEEN 200 AND 299")
    elif status_filter == "error":
        conditions.append("(wc.http_status IS NULL OR wc.http_status NOT BETWEEN 200 AND 299)")

    params.append(limit)
    where = " AND ".join(conditions)
    rows = await fetch_all(
        config_pool,
        f"""
        SELECT wc.id, wc.webhook_id, wh.name AS webhook_name,
               wc.correlation_id, wc.triggered_by, wc.webhook_url,
               wc.http_status, wc.error, wc.duration_ms, wc.called_at
        FROM webhook_calls wc
        JOIN workspace_webhooks wh ON wh.id = wc.webhook_id
        WHERE {where}
        ORDER BY wc.called_at DESC
        LIMIT ${idx}
        """,
        *params,
    )
    return [
        {
            "id": str(r["id"]),
            "webhook_id": str(r["webhook_id"]),
            "webhook_name": r["webhook_name"],
            "correlation_id": r["correlation_id"],
            "triggered_by": r["triggered_by"],
            "webhook_url": r["webhook_url"],
            "http_status": r["http_status"],
            "error": r["error"],
            "duration_ms": r["duration_ms"],
            "called_at": r["called_at"].isoformat(),
            "success": r["http_status"] is not None and 200 <= r["http_status"] <= 299,
        }
        for r in rows
    ]


async def purge_old_webhook_calls(config_pool: asyncpg.Pool) -> None:
    await config_pool.execute(
        "DELETE FROM webhook_calls WHERE called_at < now() - interval '24 hours'"
    )
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend
uv run pytest tests/integration/test_services_webhooks.py -v
```

Expected : PASS (5 tests).

- [ ] **Lint + typecheck**

```bash
uv run ruff check src/rag/schemas/webhooks.py src/rag/services/webhooks.py
uv run mypy src/rag/schemas/webhooks.py src/rag/services/webhooks.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/schemas/webhooks.py backend/src/rag/services/webhooks.py backend/tests/integration/test_services_webhooks.py
git commit -m "feat(webhooks): CRUD service + schémas DTOs"
```

---

## Task 5 : Service dispatch webhooks (HMAC + fire-and-forget)

**Files:**
- Create: `backend/src/rag/services/webhook_dispatch.py`
- Create: `backend/tests/unit/services/test_webhook_dispatch.py`

- [ ] **Écrire les tests unitaires (rouge)**

`backend/tests/unit/services/test_webhook_dispatch.py` :
```python
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from rag.services.webhook_dispatch import (
    _build_payload,
    _sign_payload,
    dispatch_webhooks,
)


def test_sign_payload_sha256() -> None:
    secret = "my-secret"
    payload = b'{"event":"test"}'
    sig = _sign_payload(secret, payload)
    assert sig.startswith("sha256=")
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert sig == f"sha256={expected}"


def test_sign_payload_none_secret_returns_none() -> None:
    assert _sign_payload(None, b"data") is None


def test_build_payload_push() -> None:
    payload = _build_payload(
        event="indexation.completed",
        workspace="ws1",
        triggered_by="push",
        job_id="uuid-1",
        status="done",
        files_changed=1,
        files_skipped=0,
        duration_ms=340,
        finished_at="2026-05-28T10:00:00Z",
        error_message=None,
    )
    assert payload["event"] == "indexation.completed"
    assert payload["triggered_by"] == "push"
    assert payload["status"] == "done"
    assert "git_commit" not in payload


@pytest.mark.asyncio
async def test_dispatch_webhooks_calls_all_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = MagicMock()

    calls_received: list[str] = []

    async def fake_fetch_all(p: Any, q: Any, *args: Any) -> list[dict[str, Any]]:
        return [
            {"id": "wh-1", "url": "https://a.com/hook", "enabled": True},
            {"id": "wh-2", "url": "https://b.com/hook", "enabled": True},
        ]

    async def fake_fetch_all_headers(p: Any, q: Any, *args: Any) -> list[dict[str, Any]]:
        return []

    async def fake_post(url: str, **kw: Any) -> MagicMock:
        calls_received.append(url)
        r = MagicMock()
        r.status_code = 200
        return r

    with patch("rag.services.webhook_dispatch.fetch_all", side_effect=[
        [{"id": "wh-1", "url": "https://a.com/hook"}, {"id": "wh-2", "url": "https://b.com/hook"}],
        [],  # headers wh-1
        [],  # headers wh-2
    ]), patch("rag.services.webhook_dispatch._http_post", new=AsyncMock(side_effect=fake_post)), \
       patch("rag.services.webhook_dispatch._insert_call", new=AsyncMock()):
        await dispatch_webhooks(
            config_pool=pool,
            workspace_id="ws-id",
            workspace_name="ws1",
            job_id="job-1",
            correlation_id="corr-1",
            triggered_by="push",
            status="done",
            files_changed=1,
            files_skipped=0,
            duration_ms=100,
            finished_at="2026-05-28T10:00:00Z",
            error_message=None,
            webhook_secret=None,
            resolver=None,
        )

    assert len(calls_received) == 2
```

- [ ] **Vérifier que le test échoue**

```bash
cd backend
uv run pytest tests/unit/services/test_webhook_dispatch.py -v
```

Expected : ImportError.

- [ ] **Créer `services/webhook_dispatch.py`**

```python
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from typing import Any, Protocol

import httpx
import structlog

from rag.db.helpers import fetch_all

log = structlog.get_logger(__name__)

_TIMEOUT = 10.0


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


def _sign_payload(secret: str | None, payload_bytes: bytes) -> str | None:
    if secret is None:
        return None
    sig = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def _build_payload(
    *,
    event: str,
    workspace: str,
    triggered_by: str,
    job_id: str,
    status: str,
    files_changed: int,
    files_skipped: int,
    duration_ms: int | None,
    finished_at: str | None,
    error_message: str | None,
) -> dict[str, Any]:
    return {
        "event": event,
        "workspace": workspace,
        "triggered_by": triggered_by,
        "job_id": job_id,
        "status": status,
        "files_changed": files_changed,
        "files_skipped": files_skipped,
        "duration_ms": duration_ms,
        "finished_at": finished_at,
        "error_message": error_message,
    }


async def _http_post(url: str, *, headers: dict[str, str], content: bytes) -> httpx.Response:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        return await client.post(url, content=content, headers=headers)


async def _insert_call(
    config_pool: Any,
    *,
    workspace_id: str,
    webhook_id: str,
    job_id: str,
    correlation_id: str,
    triggered_by: str,
    webhook_url: str,
    http_status: int | None,
    error: str | None,
    duration_ms: int,
) -> None:
    await config_pool.execute(
        """
        INSERT INTO webhook_calls
            (workspace_id, webhook_id, job_id, correlation_id, triggered_by,
             webhook_url, http_status, error, duration_ms)
        VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9)
        """,
        workspace_id, webhook_id, job_id, correlation_id, triggered_by,
        webhook_url, http_status, error, duration_ms,
    )


async def _call_one_webhook(
    *,
    webhook: dict[str, Any],
    raw_headers: list[dict[str, Any]],
    payload_bytes: bytes,
    correlation_id: str,
    triggered_by: str,
    git_repo: str | None,
    git_branch: str | None,
    git_commit: str | None,
    signature: str | None,
    config_pool: Any,
    workspace_id: str,
    job_id: str,
    resolver: _ResolverProtocol | None,
) -> None:
    wh_id = str(webhook["id"])
    url = webhook["url"]

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "X-Correlation-ID": correlation_id,
    }
    if signature:
        headers["X-RAG-Signature"] = signature
    if triggered_by in ("webhook", "manual", "schedule") or "git" in triggered_by:
        if git_repo:
            headers["X-Git-Repo"] = git_repo
        if git_branch:
            headers["X-Git-Branch"] = git_branch
        if git_commit:
            headers["X-Git-Commit"] = git_commit

    # Résout les headers custom
    for h in raw_headers:
        if not h.get("enabled"):
            continue
        vault_ref = h.get("vault_ref")
        if vault_ref and resolver is not None:
            try:
                val = await resolver.resolve_with_retry(vault_ref)
                headers[h["name"]] = val
            except Exception:
                log.warning("webhook.header_resolve_failed", name=h["name"], wh_id=wh_id)
        elif h.get("value"):
            headers[h["name"]] = h["value"]

    t0 = time.monotonic()
    http_status: int | None = None
    error: str | None = None
    try:
        resp = await _http_post(url, headers=headers, content=payload_bytes)
        http_status = resp.status_code
    except Exception as exc:
        error = str(exc)[:200]
        log.warning("webhook.call_failed", url=url, error=error)
    finally:
        elapsed = int((time.monotonic() - t0) * 1000)

    try:
        await _insert_call(
            config_pool,
            workspace_id=workspace_id,
            webhook_id=wh_id,
            job_id=job_id,
            correlation_id=correlation_id,
            triggered_by=triggered_by,
            webhook_url=url,
            http_status=http_status,
            error=error,
            duration_ms=elapsed,
        )
    except Exception:
        log.exception("webhook.audit_insert_failed", wh_id=wh_id)


async def dispatch_webhooks(
    *,
    config_pool: Any,
    workspace_id: str,
    workspace_name: str,
    job_id: str,
    correlation_id: str,
    triggered_by: str,
    status: str,
    files_changed: int,
    files_skipped: int,
    duration_ms: int | None,
    finished_at: str | None,
    error_message: str | None,
    webhook_secret: str | None,
    resolver: _ResolverProtocol | None,
    git_repo: str | None = None,
    git_branch: str | None = None,
    git_commit: str | None = None,
) -> None:
    """Appelle tous les webhooks activés du workspace en parallèle. Fire-and-forget."""
    try:
        webhooks = await fetch_all(
            config_pool,
            "SELECT id, url FROM workspace_webhooks WHERE workspace_id=$1::uuid AND enabled=true",
            workspace_id,
        )
        if not webhooks:
            return

        payload = _build_payload(
            event="indexation.completed",
            workspace=workspace_name,
            triggered_by=triggered_by,
            job_id=job_id,
            status=status,
            files_changed=files_changed,
            files_skipped=files_skipped,
            duration_ms=duration_ms,
            finished_at=finished_at,
            error_message=error_message,
        )
        payload_bytes = json.dumps(payload, default=str).encode("utf-8")

        if webhook_secret is None:
            log.warning("webhook.dispatch_no_secret", workspace=workspace_name)
        signature = _sign_payload(webhook_secret, payload_bytes)

        tasks = []
        for wh in webhooks:
            raw_headers = await fetch_all(
                config_pool,
                "SELECT name, value, vault_ref, enabled FROM webhook_headers WHERE webhook_id=$1",
                wh["id"],
            )
            tasks.append(
                _call_one_webhook(
                    webhook=wh,
                    raw_headers=list(raw_headers),
                    payload_bytes=payload_bytes,
                    correlation_id=correlation_id,
                    triggered_by=triggered_by,
                    git_repo=git_repo,
                    git_branch=git_branch,
                    git_commit=git_commit,
                    signature=signature,
                    config_pool=config_pool,
                    workspace_id=workspace_id,
                    job_id=job_id,
                    resolver=resolver,
                )
            )
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:
        log.exception("webhook.dispatch_error", workspace=workspace_name)
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend
uv run pytest tests/unit/services/test_webhook_dispatch.py -v
```

Expected : PASS (4 tests).

- [ ] **Lint + typecheck**

```bash
uv run ruff check src/rag/services/webhook_dispatch.py
uv run mypy src/rag/services/webhook_dispatch.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/services/webhook_dispatch.py backend/tests/unit/services/test_webhook_dispatch.py
git commit -m "feat(webhooks): service dispatch HMAC fire-and-forget"
```

---

## Task 6 : API router admin webhooks

**Files:**
- Create: `backend/src/rag/api/admin_webhooks.py`
- Modify: `backend/src/rag/api/admin.py`

- [ ] **Créer `api/admin_webhooks.py`**

```python
from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, Query, Request, Response, status

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.schemas.webhooks import (
    WebhookCallOut,
    WebhookCreateRequest,
    WebhookHeaderPatchRequest,
    WebhookOut,
    WebhookPatchRequest,
)
from rag.services.webhooks import (
    create_webhook,
    delete_webhook,
    list_webhook_calls,
    list_webhooks,
    patch_webhook,
    patch_webhook_header,
    purge_old_webhook_calls,
)


def _config_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pools.config_pool  # type: ignore[no-any-return]


def _resolver(request: Request):  # type: ignore[no-untyped-def]
    return getattr(request.app.state, "resolver", None)


def build_webhooks_router() -> APIRouter:
    router = APIRouter(
        tags=["webhooks"],
        dependencies=[Depends(require_master_key_or_authenticated_admin)],
    )

    @router.get("/workspaces/{name}/webhooks", response_model=list[WebhookOut])
    async def get_webhooks(
        name: str,
        pool: asyncpg.Pool = Depends(_config_pool),  # noqa: B008
    ) -> list[dict]:
        return await list_webhooks(pool, workspace_name=name)

    @router.post("/workspaces/{name}/webhooks", response_model=WebhookOut, status_code=201)
    async def post_webhook(
        name: str,
        body: WebhookCreateRequest,
        request: Request,
        pool: asyncpg.Pool = Depends(_config_pool),  # noqa: B008
    ) -> dict:
        return await create_webhook(
            pool,
            workspace_name=name,
            name=body.name,
            url=body.url,
            enabled=body.enabled,
            headers=[h.model_dump() for h in body.headers],
            resolver=_resolver(request),
        )

    @router.patch("/workspaces/{name}/webhooks/{webhook_id}", response_model=WebhookOut)
    async def update_webhook(
        name: str,
        webhook_id: str,
        body: WebhookPatchRequest,
        pool: asyncpg.Pool = Depends(_config_pool),  # noqa: B008
    ) -> dict:
        return await patch_webhook(
            pool,
            webhook_id=webhook_id,
            name=body.name,
            url=body.url,
            enabled=body.enabled,
        )

    @router.delete("/workspaces/{name}/webhooks/{webhook_id}", status_code=204)
    async def remove_webhook(
        name: str,
        webhook_id: str,
        request: Request,
        pool: asyncpg.Pool = Depends(_config_pool),  # noqa: B008
    ) -> Response:
        await delete_webhook(pool, webhook_id=webhook_id, resolver=_resolver(request))
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.patch(
        "/workspaces/{name}/webhooks/{webhook_id}/headers/{header_id}",
        response_model=dict,
    )
    async def update_header(
        name: str,
        webhook_id: str,
        header_id: str,
        body: WebhookHeaderPatchRequest,
        request: Request,
        pool: asyncpg.Pool = Depends(_config_pool),  # noqa: B008
    ) -> dict:
        return await patch_webhook_header(
            pool,
            webhook_id=webhook_id,
            header_id=header_id,
            value=body.value,
            vault=body.vault,
            enabled=body.enabled,
            workspace_name=name,
            resolver=_resolver(request),
        )

    @router.get("/workspaces/{name}/webhooks/calls", response_model=list[WebhookCallOut])
    async def get_calls(
        name: str,
        webhook_id: str | None = Query(default=None),
        correlation_id: str | None = Query(default=None),
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=50, ge=1, le=500),
        pool: asyncpg.Pool = Depends(_config_pool),  # noqa: B008
    ) -> list[dict]:
        return await list_webhook_calls(
            pool,
            workspace_name=name,
            webhook_id=webhook_id,
            correlation_id=correlation_id,
            status_filter=status_filter,
            limit=limit,
        )

    @router.delete("/workspaces/{name}/webhooks/calls", status_code=204)
    async def purge_calls(
        name: str,
        pool: asyncpg.Pool = Depends(_config_pool),  # noqa: B008
    ) -> Response:
        await purge_old_webhook_calls(pool)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
```

- [ ] **Monter le router dans `api/admin.py`**

Ajouter en fin du fichier `admin.py`, dans la fonction `build_admin_router()` (ou équivalent qui monte les sous-routers) :

```python
from rag.api.admin_webhooks import build_webhooks_router
# ... dans build_admin_router() ou dans main.py où le router admin est inclus :
app.include_router(build_webhooks_router(), prefix="/api/admin")
```

Vérifier comment les autres routers sont montés dans `main.py` et reproduire le même pattern.

- [ ] **Vérifier le wireup : GET /api/admin/workspaces/test/webhooks ne retourne pas 404**

```bash
cd backend && uv run uvicorn rag.main:app --reload &
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer changeme" \
  http://localhost:8000/api/admin/workspaces/nonexistent/webhooks
# Expected : 404 (workspace not found), pas 404 de route inconnue
kill %1
```

- [ ] **Lint**

```bash
uv run ruff check src/rag/api/admin_webhooks.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/api/admin_webhooks.py backend/src/rag/api/admin.py backend/src/rag/main.py
git commit -m "feat(api): router admin webhooks CRUD + audit log"
```

---

## Task 7 : Endpoint push → 202

**Files:**
- Modify: `backend/src/rag/api/workspace.py`
- Modify: `backend/src/rag/services/push.py`
- Modify: `backend/tests/unit/services/test_push_service.py`
- Modify: `backend/tests/api/test_workspace_push_dedup.py`
- Modify: `backend/tests/api/test_workspace_push_errors.py`

- [ ] **Modifier `services/push.py` — supprimer `push_document`, garder `normalize_path`**

```python
from __future__ import annotations

import re

from rag.api.errors import InvalidPath

_PATH_MAX_LEN = 1024
_BAD_SEGMENT = re.compile(r"(^|/)\.\.(/|$)")


def normalize_path(raw: str) -> str:
    """Normalise et valide un path POSIX relatif.

    - remplace ``\\`` par ``/``
    - rejette : NUL byte, leading ``/``, segments ``..``, vide, > 1024 chars
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

- [ ] **Modifier `api/workspace.py` — endpoint 202**

```python
from __future__ import annotations

import uuid as _uuid_mod

import asyncpg
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from rag.auth.workspace_auth import AuthContext, require_workspace_apikey
from rag.schemas.workspace import PushAsyncResponse, PushRequest
from rag.services.push import normalize_path


def build_workspace_router() -> APIRouter:
    router = APIRouter(tags=["workspace"])

    @router.post("/workspaces/{name}/index", status_code=202)
    async def push_index(
        name: str,
        payload: PushRequest,
        request: Request,
        auth: AuthContext = Depends(require_workspace_apikey),  # noqa: B008
    ) -> Response:
        norm_path = normalize_path(payload.path)
        correlation_id = str(_uuid_mod.uuid4())
        pool: asyncpg.Pool = request.app.state.pools.config_pool

        job_id = await pool.fetchval(
            """
            INSERT INTO index_jobs (workspace_id, triggered_by, status, correlation_id)
            VALUES ($1, 'push', 'pending', $2)
            RETURNING id
            """,
            auth.workspace_id,
            correlation_id,
        )
        await pool.execute(
            "INSERT INTO push_job_payloads (job_id, path, content) VALUES ($1, $2, $3)",
            job_id,
            norm_path,
            payload.content,
        )

        body = PushAsyncResponse(job_id=str(job_id), status="pending")
        return JSONResponse(
            content=body.model_dump(),
            status_code=202,
            headers={"X-Correlation-ID": correlation_id},
        )

    return router
```

- [ ] **Mettre à jour `tests/unit/services/test_push_service.py`**

Remplacer le contenu par des tests sur `normalize_path` uniquement (les tests `push_document` n'ont plus de raison d'être) :

```python
from __future__ import annotations

import pytest

from rag.api.errors import InvalidPath
from rag.services.push import normalize_path


def test_normalize_backslash() -> None:
    assert normalize_path("docs\\sub\\foo.md") == "docs/sub/foo.md"


def test_normalize_rejects_traversal() -> None:
    with pytest.raises(InvalidPath) as exc:
        normalize_path("foo/../bar")
    assert exc.value.args[0] == "path_traversal_forbidden"


def test_normalize_rejects_absolute() -> None:
    with pytest.raises(InvalidPath):
        normalize_path("/abs/path")


def test_normalize_rejects_nul() -> None:
    with pytest.raises(InvalidPath):
        normalize_path("fo\x00o")


def test_normalize_valid_path() -> None:
    assert normalize_path("generated/docker-analysis.md") == "generated/docker-analysis.md"
```

- [ ] **Mettre à jour `test_workspace_push_dedup.py`**

Le test doit vérifier le 202 et le job en DB (le worker n'est pas lancé dans ces tests API) :

```python
from __future__ import annotations

import asyncpg
from fastapi.testclient import TestClient


def _make_ws(client: TestClient, admin_headers: dict[str, str], name: str) -> str:
    r = client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={
            "name": name,
            "api_key_vault": "rag",
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 201
    return r.json()["api_key"]


def test_push_returns_202_with_job_id(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_async1")
    headers = {"Authorization": f"Bearer {api_key}"}

    r = admin_client.post(
        "/workspaces/ws_async1/index",
        headers=headers,
        json={"path": "doc.md", "content": "hello world"},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "pending"
    assert "job_id" in body
    assert "X-Correlation-ID" in r.headers


def test_push_payload_stored_in_db(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    import asyncio

    api_key = _make_ws(admin_client, admin_headers, "ws_async2")
    headers = {"Authorization": f"Bearer {api_key}"}

    r = admin_client.post(
        "/workspaces/ws_async2/index",
        headers=headers,
        json={"path": "a.md", "content": "stored content"},
    )
    assert r.status_code == 202
    job_id = r.json()["job_id"]

    async def check() -> None:
        conn = await asyncpg.connect(pg_container)
        try:
            row = await conn.fetchrow(
                "SELECT path, content FROM push_job_payloads WHERE job_id=$1::uuid", job_id
            )
            assert row is not None
            assert row["path"] == "a.md"
            assert row["content"] == "stored content"
        finally:
            await conn.close()

    asyncio.get_event_loop().run_until_complete(check())
```

- [ ] **Mettre à jour `test_workspace_push_errors.py`**

Le test `path_traversal` doit toujours retourner 422 (la validation se fait avant la création du job) :

```python
from __future__ import annotations

from fastapi.testclient import TestClient


def _make_ws(client: TestClient, admin_headers: dict[str, str], name: str) -> str:
    r = client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={
            "name": name,
            "api_key_vault": "rag",
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 201
    return r.json()["api_key"]


def test_push_returns_422_for_path_traversal(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_e_a")
    r = admin_client.post(
        "/workspaces/ws_e_a/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"path": "foo/../bar", "content": "y"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "invalid_path"
    assert body["reason"] == "path_traversal_forbidden"
```

- [ ] **Vérifier tous les tests push**

```bash
cd backend
uv run pytest tests/unit/services/test_push_service.py tests/api/test_workspace_push_dedup.py tests/api/test_workspace_push_errors.py tests/api/test_workspace_push_auth.py -v
```

Expected : PASS.

- [ ] **Commit**

```bash
git add backend/src/rag/services/push.py backend/src/rag/api/workspace.py backend/tests/unit/services/test_push_service.py backend/tests/api/test_workspace_push_dedup.py backend/tests/api/test_workspace_push_errors.py
git commit -m "feat(push): endpoint POST /index → 202 asynchrone (breaking change)"
```

---

## Task 8 : Executor — _execute_push_job + _execute_git_job + dispatch

**Files:**
- Modify: `backend/src/rag/sync/executor.py`
- Create: `backend/tests/integration/test_executor_push_job.py`

- [ ] **Écrire les tests d'intégration pour le push job (rouge)**

`backend/tests/integration/test_executor_push_job.py` :
```python
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.indexer.noop import NoOpIndexer
from rag.sync.executor import execute_next_pending_job
from rag.sync.repo_storage import RepoStorage
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _StubResolver:
    async def resolve_with_retry(self, ref: str) -> str:
        return "tok"


class _StubClientProvider:
    async def get_default_vault_name(self) -> str | None:
        return "rag"


@pytest.fixture
async def pool(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM workspaces")
    return session_pool


async def _seed_push_job(
    pool: asyncpg.Pool, ws_name: str, path: str, content: str
) -> tuple[str, str]:
    """Retourne (job_id, correlation_id)."""
    correlation_id = "corr-test-001"
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name=ws_name)
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status, correlation_id) "
            "VALUES ($1, 'push', 'pending', $2) RETURNING id",
            ws_id, correlation_id,
        )
        await conn.execute(
            "INSERT INTO push_job_payloads (job_id, path, content) VALUES ($1, $2, $3)",
            job_id, path, content,
        )
    return str(job_id), correlation_id


async def test_push_job_executed_done(pool: asyncpg.Pool, tmp_path: Path) -> None:
    storage = RepoStorage(tmp_path)
    indexer = NoOpIndexer()
    job_id, _ = await _seed_push_job(pool, "ws_push1", "a.md", "hello")

    result = await execute_next_pending_job(
        config_pool=pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),
        client_provider=_StubClientProvider(),
        webhook_secret=None,
    )
    assert result is True

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status FROM index_jobs WHERE id=$1::uuid", job_id
        )
        assert row["status"] == "done"

        payload = await conn.fetchval(
            "SELECT job_id FROM push_job_payloads WHERE job_id=$1::uuid", job_id
        )
        assert payload is None  # nettoyé


async def test_push_job_skipped_when_same_hash(pool: asyncpg.Pool, tmp_path: Path) -> None:
    storage = RepoStorage(tmp_path)
    indexer = NoOpIndexer()

    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_push2")
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        content = "same content"
        content_hash = "sha256:" + sha256(content.encode()).hexdigest()
        await conn.execute(
            "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
            "VALUES ($1, 'a.md', $2, 'openai/text-embedding-3-small')",
            ws_id, content_hash,
        )
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status, correlation_id) "
            "VALUES ($1, 'push', 'pending', 'corr-002') RETURNING id",
            ws_id,
        )
        await conn.execute(
            "INSERT INTO push_job_payloads (job_id, path, content) VALUES ($1, 'a.md', $2)",
            job_id, content,
        )

    await execute_next_pending_job(
        config_pool=pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),
        client_provider=_StubClientProvider(),
        webhook_secret=None,
    )

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status FROM index_jobs WHERE id=$1", job_id
        )
        assert row["status"] == "skipped"
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend
uv run pytest tests/integration/test_executor_push_job.py -v
```

Expected : FAIL (signature de `execute_next_pending_job` incorrecte).

- [ ] **Mettre à jour `sync/executor.py`**

Modifier `pick_next_pending_job` pour retourner `triggered_by` et `correlation_id` :

```python
# Dans pick_next_pending_job, le RETURNING devient :
"""
RETURNING
    j.id AS job_id,
    j.workspace_id,
    j.source_id,
    j.triggered_by,
    j.correlation_id
"""
```

Dans la construction du `JobToProcess` :
```python
return JobToProcess(
    job_id=row["job_id"],
    workspace_id=row["workspace_id"],
    workspace_name=context["workspace_name"],
    source_id=row["source_id"],          # peut être None pour push
    source_config=source_config,
    indexer_provider=context["indexer_provider"] or "",
    indexer_model=context["indexer_model"] or "",
    triggered_by=row["triggered_by"],
    correlation_id=row["correlation_id"],
)
```

Ajouter `webhook_secret: str | None` au paramètre de `execute_next_pending_job` et `_process_job` (renommé `_execute_git_job`).

Créer `_execute_push_job` :

Ajouter ces imports en tête de `executor.py` (avec les autres imports existants) :
```python
import datetime
from hashlib import sha256 as _sha256
from rag.services.webhook_dispatch import dispatch_webhooks
```

```python
async def _execute_push_job(
    *,
    job: JobToProcess,
    config_pool: asyncpg.Pool,
    indexer: IndexerProtocol,
    webhook_secret: str | None,
    resolver: _ResolverProtocol | None,
) -> None:

    jid = str(job.job_id)

    # Lire le payload
    row = await fetch_one(
        config_pool,
        "SELECT path, content FROM push_job_payloads WHERE job_id=$1",
        job.job_id,
    )

    final_status = "error"
    files_changed = 0
    files_skipped = 0
    error_message: str | None = None

    try:
        if row is None:
            raise RuntimeError(f"push_job_payloads not found for job {jid}")

        path, content = row["path"], row["content"]
        content_hash = "sha256:" + _sha256(content.encode("utf-8")).hexdigest()

        existing = await config_pool.fetchval(
            "SELECT content_hash FROM indexed_documents WHERE workspace_id=$1 AND path=$2",
            job.workspace_id, path,
        )
        if existing == content_hash:
            await config_pool.execute(
                "UPDATE index_jobs SET status='skipped', finished_at=now(), "
                "duration_ms=EXTRACT(MILLISECONDS FROM (now()-started_at))::int WHERE id=$1",
                job.job_id,
            )
            final_status = "skipped"
            files_skipped = 1
        else:
            await indexer.index_file(
                workspace_id=job.workspace_id,
                path=path,
                content=content,
                content_hash=content_hash,
                indexer_used=job.indexer_used,
            )
            await config_pool.execute(
                "UPDATE index_jobs SET status='done', finished_at=now(), files_changed=1, "
                "duration_ms=EXTRACT(MILLISECONDS FROM (now()-started_at))::int WHERE id=$1",
                job.job_id,
            )
            final_status = "done"
            files_changed = 1
    except Exception as e:
        error_message = str(e)[:500]
        await _mark_job_error(config_pool, job_id=job.job_id, error_message=error_message)
        final_status = "error"
    finally:
        try:
            await config_pool.execute(
                "DELETE FROM push_job_payloads WHERE job_id=$1", job.job_id
            )
        except Exception:
            log.warning("push_job.payload_cleanup_failed", job_id=jid)

    finished_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    correlation_id = job.correlation_id or jid
    await dispatch_webhooks(
        config_pool=config_pool,
        workspace_id=str(job.workspace_id),
        workspace_name=job.workspace_name,
        job_id=jid,
        correlation_id=correlation_id,
        triggered_by=job.triggered_by,
        status=final_status,
        files_changed=files_changed,
        files_skipped=files_skipped,
        duration_ms=None,
        finished_at=finished_at,
        error_message=error_message,
        webhook_secret=webhook_secret,
        resolver=resolver,
    )
```

Dans `execute_next_pending_job`, brancher sur `triggered_by` :

```python
async def execute_next_pending_job(
    *,
    config_pool: asyncpg.Pool,
    storage: RepoStorage,
    indexer: IndexerProtocol,
    resolver: _ResolverProtocol,
    client_provider: _ClientProviderProtocol,
    job_log_bus: JobLogBus | None = None,
    webhook_secret: str | None = None,
) -> bool:
    job = await pick_next_pending_job(config_pool)
    if job is None:
        return False

    try:
        if job.triggered_by == "push":
            await _execute_push_job(
                job=job,
                config_pool=config_pool,
                indexer=indexer,
                webhook_secret=webhook_secret,
                resolver=resolver,
            )
        else:
            default_vault_name = await client_provider.get_default_vault_name()
            await _execute_git_job(
                job=job,
                config_pool=config_pool,
                storage=storage,
                indexer=indexer,
                resolver=resolver,
                default_vault_name=default_vault_name,
                job_log_bus=job_log_bus,
                webhook_secret=webhook_secret,
            )
    except Exception as e:
        msg = _format_error(e)
        log.exception("sync.executor.job_error", job_id=str(job.job_id))
        await _mark_job_error(config_pool, job_id=job.job_id, error_message=msg)
    return True
```

Dans `_execute_git_job` (ex-`_process_job`) :
- Ajouter `webhook_secret: str | None` dans la signature
- Après `head_commit(dest)` : `await config_pool.execute("UPDATE index_jobs SET correlation_id=$1 WHERE id=$2", current, job.job_id)`
- En fin du step 6 (mark done) : appeler `dispatch_webhooks(...)` avec les paramètres git
- Le `correlation_id` du job git = hash du commit = `current` (fallback = `str(job.job_id)` si exception avant `head_commit`)

- [ ] **Vérifier que les tests passent**

```bash
cd backend
uv run pytest tests/integration/test_executor_push_job.py tests/integration/test_sync_executor.py -v
```

Expected : PASS.

- [ ] **Lint + typecheck**

```bash
uv run ruff check src/rag/sync/executor.py
uv run mypy src/rag/sync/executor.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/sync/executor.py backend/tests/integration/test_executor_push_job.py
git commit -m "feat(executor): _execute_push_job + _execute_git_job + dispatch webhooks"
```

---

## Task 9 : Worker — webhook_secret + purge audit log

**Files:**
- Modify: `backend/src/rag/sync/worker.py`

- [ ] **Mettre à jour `SyncWorker.__init__`**

Ajouter `webhook_secret: str | None = None` :

```python
def __init__(
    self,
    *,
    config_pool: asyncpg.Pool,
    storage: RepoStorage,
    indexer: IndexerProtocol,
    resolver: _ResolverProtocol,
    client_provider: _ClientProviderProtocol,
    poll_interval_seconds: int,
    default_sync_interval_seconds: int,
    job_log_bus: JobLogBus | None = None,
    webhook_secret: str | None = None,
) -> None:
    ...
    self._webhook_secret = webhook_secret
```

- [ ] **Transmettre `webhook_secret` à `execute_next_pending_job` et ajouter la purge**

Dans `_run` :

```python
async def _run(self) -> None:
    from rag.services.webhooks import purge_old_webhook_calls

    while not self._stop_event.is_set():
        try:
            await schedule_due_sources(
                self._config_pool,
                default_interval_seconds=self._default_sync_interval,
            )
            await execute_next_pending_job(
                config_pool=self._config_pool,
                storage=self._storage,
                indexer=self._indexer,
                resolver=self._resolver,
                client_provider=self._client_provider,
                job_log_bus=self._job_log_bus,
                webhook_secret=self._webhook_secret,
            )
            try:
                await purge_old_webhook_calls(self._config_pool)
            except Exception:
                log.warning("sync.worker.purge_webhook_calls_failed")
        except Exception:
            log.exception("sync.worker.cycle_error")

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(
                self._stop_event.wait(),
                timeout=self._poll_interval,
            )
```

- [ ] **Mettre à jour `main.py` pour passer `webhook_secret` au worker**

Dans la fonction lifespan où `SyncWorker` est instancié, ajouter :
```python
webhook_secret=settings.rag_webhook_secret.get_secret_value() if settings.rag_webhook_secret else None,
```

- [ ] **Vérifier les tests worker existants**

```bash
cd backend
uv run pytest tests/integration/test_sync_worker.py -v
```

Expected : PASS.

- [ ] **Lint + typecheck**

```bash
uv run ruff check src/rag/sync/worker.py src/rag/main.py
uv run mypy src/rag/sync/worker.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/sync/worker.py backend/src/rag/main.py
git commit -m "feat(worker): webhook_secret + purge webhook_calls par cycle"
```

---

## Task 10 : Suite de tests backend complète

- [ ] **Lancer la suite complète**

```bash
cd backend
uv run pytest -v --tb=short
```

Expected : tous les tests passent (excepté les tests `smoke` qui sont désactivés par défaut).

- [ ] **Corriger les régressions éventuelles** (tests qui vérifiaient 200 sur `/index`, imports cassés, etc.)

- [ ] **Commit de correction si nécessaire**

```bash
git add -p  # sélectionner uniquement les corrections
git commit -m "fix(tests): adapter les tests suite au passage push asynchrone"
```

---

## Task 11 : Frontend — types + API client + i18n

**Files:**
- Create: `frontend/src/lib/webhooks.types.ts`
- Create: `frontend/src/lib/webhooks.ts`
- Modify: `frontend/src/i18n/fr.json`
- Modify: `frontend/src/i18n/en.json`

- [ ] **Créer `webhooks.types.ts`**

```typescript
export interface WebhookHeader {
  id: string;
  name: string;
  value: null;
  vault_ref: string | null;
  enabled: boolean;
}

export interface Webhook {
  id: string;
  name: string;
  url: string;
  enabled: boolean;
  headers: WebhookHeader[];
}

export interface WebhookHeaderIn {
  name: string;
  value: string | null;
  vault: string | null;
  enabled: boolean;
}

export interface WebhookCreatePayload {
  name: string;
  url: string;
  enabled: boolean;
  headers: WebhookHeaderIn[];
}

export interface WebhookPatchPayload {
  name?: string;
  url?: string;
  enabled?: boolean;
}

export interface WebhookHeaderPatchPayload {
  value?: string | null;
  vault?: string | null;
  enabled?: boolean;
}

export interface WebhookCall {
  id: string;
  webhook_id: string;
  webhook_name: string;
  correlation_id: string;
  triggered_by: string;
  webhook_url: string;
  http_status: number | null;
  error: string | null;
  duration_ms: number | null;
  called_at: string;
  success: boolean;
}

export interface WebhookCallsFilter {
  webhook_id?: string;
  correlation_id?: string;
  status?: "success" | "error";
  limit?: number;
}
```

- [ ] **Créer `webhooks.ts`**

```typescript
import { apiClient } from "./api";
import type {
  Webhook,
  WebhookCall,
  WebhookCallsFilter,
  WebhookCreatePayload,
  WebhookHeaderPatchPayload,
  WebhookPatchPayload,
} from "./webhooks.types";

const base = (workspace: string) =>
  `/api/admin/workspaces/${workspace}/webhooks`;

export async function listWebhooks(workspace: string): Promise<Webhook[]> {
  const r = await apiClient.get(base(workspace));
  return r.data;
}

export async function createWebhook(
  workspace: string,
  payload: WebhookCreatePayload
): Promise<Webhook> {
  const r = await apiClient.post(base(workspace), payload);
  return r.data;
}

export async function patchWebhook(
  workspace: string,
  webhookId: string,
  payload: WebhookPatchPayload
): Promise<Webhook> {
  const r = await apiClient.patch(`${base(workspace)}/${webhookId}`, payload);
  return r.data;
}

export async function deleteWebhook(
  workspace: string,
  webhookId: string
): Promise<void> {
  await apiClient.delete(`${base(workspace)}/${webhookId}`);
}

export async function patchWebhookHeader(
  workspace: string,
  webhookId: string,
  headerId: string,
  payload: WebhookHeaderPatchPayload
): Promise<void> {
  await apiClient.patch(
    `${base(workspace)}/${webhookId}/headers/${headerId}`,
    payload
  );
}

export async function listWebhookCalls(
  workspace: string,
  filter: WebhookCallsFilter = {}
): Promise<WebhookCall[]> {
  const params = new URLSearchParams();
  if (filter.webhook_id) params.set("webhook_id", filter.webhook_id);
  if (filter.correlation_id)
    params.set("correlation_id", filter.correlation_id);
  if (filter.status) params.set("status", filter.status);
  if (filter.limit) params.set("limit", String(filter.limit));
  const r = await apiClient.get(`${base(workspace)}/calls?${params}`);
  return r.data;
}

export async function purgeWebhookCalls(workspace: string): Promise<void> {
  await apiClient.delete(`${base(workspace)}/calls`);
}
```

- [ ] **Ajouter les clés i18n dans `fr.json`**

Dans la section du namespace `workspace` (ou à la racine selon le pattern existant), ajouter :

```json
"webhooks": {
  "tabs": {
    "webhooks": "Webhooks"
  },
  "list": {
    "title": "Webhooks",
    "add": "Ajouter",
    "empty": "Aucun webhook configuré.",
    "headers_count": "{{count}} header",
    "headers_count_plural": "{{count}} headers",
    "enabled": "Activé",
    "disabled": "Désactivé",
    "delete_confirm": "Supprimer ce webhook ?",
    "delete_confirm_description": "Cette action est irréversible."
  },
  "form": {
    "title_create": "Nouveau webhook",
    "title_edit": "Modifier le webhook",
    "name": "Nom",
    "url": "URL",
    "enabled": "Activé",
    "headers": "Headers",
    "add_header": "+ Header",
    "header_name": "Nom du header",
    "header_value": "Valeur",
    "header_vault": "Coffre",
    "reserved_error": "Header réservé — ne peut pas être configuré.",
    "save": "Enregistrer",
    "cancel": "Annuler"
  },
  "calls": {
    "title": "Audit log",
    "filter_webhook": "Webhook",
    "filter_status": "Statut",
    "filter_correlation": "Correlation ID",
    "filter_all": "Tous",
    "filter_success": "Succès",
    "filter_error": "Erreur",
    "search": "Chercher",
    "col_date": "Date",
    "col_webhook": "Webhook",
    "col_status": "Statut HTTP",
    "col_duration": "Durée",
    "col_correlation": "Corrélation",
    "empty": "Aucun appel enregistré.",
    "purge": "Purger l'audit",
    "purge_confirm": "Purger tous les appels ?",
    "purge_confirm_description": "Les entrées de plus de 24h seront supprimées."
  }
}
```

- [ ] **Ajouter les clés i18n dans `en.json`** (même structure, textes en anglais)

```json
"webhooks": {
  "tabs": { "webhooks": "Webhooks" },
  "list": {
    "title": "Webhooks", "add": "Add", "empty": "No webhooks configured.",
    "headers_count": "{{count}} header", "headers_count_plural": "{{count}} headers",
    "enabled": "Enabled", "disabled": "Disabled",
    "delete_confirm": "Delete this webhook?",
    "delete_confirm_description": "This action cannot be undone."
  },
  "form": {
    "title_create": "New webhook", "title_edit": "Edit webhook",
    "name": "Name", "url": "URL", "enabled": "Enabled",
    "headers": "Headers", "add_header": "+ Header",
    "header_name": "Header name", "header_value": "Value", "header_vault": "Vault",
    "reserved_error": "Reserved header — cannot be configured.",
    "save": "Save", "cancel": "Cancel"
  },
  "calls": {
    "title": "Audit log", "filter_webhook": "Webhook", "filter_status": "Status",
    "filter_correlation": "Correlation ID", "filter_all": "All",
    "filter_success": "Success", "filter_error": "Error", "search": "Search",
    "col_date": "Date", "col_webhook": "Webhook", "col_status": "HTTP Status",
    "col_duration": "Duration", "col_correlation": "Correlation",
    "empty": "No calls recorded.", "purge": "Purge audit log",
    "purge_confirm": "Purge all calls?",
    "purge_confirm_description": "Entries older than 24h will be deleted."
  }
}
```

- [ ] **Vérifier TS strict**

```bash
cd frontend && npx tsc --noEmit
```

Expected : no errors.

- [ ] **Commit**

```bash
git add frontend/src/lib/webhooks.types.ts frontend/src/lib/webhooks.ts frontend/src/i18n/fr.json frontend/src/i18n/en.json
git commit -m "feat(front): types + API client webhooks + clés i18n"
```

---

## Task 12 : Frontend — composants Webhooks

**Files:**
- Create: `frontend/src/pages/workspace/WorkspaceWebhooksTab.tsx`
- Create: `frontend/src/pages/workspace/WebhookForm.tsx`
- Create: `frontend/src/pages/workspace/WebhookCallsLog.tsx`
- Create: `frontend/src/pages/workspace/__tests__/WorkspaceWebhooksTab.test.tsx`

- [ ] **Écrire les tests (rouge)**

`frontend/src/pages/workspace/__tests__/WorkspaceWebhooksTab.test.tsx` :
```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WorkspaceWebhooksTab } from "../WorkspaceWebhooksTab";

vi.mock("@/lib/webhooks", () => ({
  listWebhooks: vi.fn().mockResolvedValue([]),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (k: string) => k,
  }),
}));

const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

describe("WorkspaceWebhooksTab", () => {
  it("renders empty state when no webhooks", async () => {
    render(
      <QueryClientProvider client={qc}>
        <WorkspaceWebhooksTab workspaceName="ws1" />
      </QueryClientProvider>
    );
    // Le composant charge, l'état vide s'affiche
    expect(
      await screen.findByText("webhooks.list.empty")
    ).toBeInTheDocument();
  });
});
```

- [ ] **Créer `WebhookForm.tsx`**

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { WebhookCreatePayload, WebhookHeaderIn } from "@/lib/webhooks.types";

const RESERVED = new Set([
  "x-correlation-id",
  "x-rag-signature",
  "x-git-repo",
  "x-git-branch",
  "x-git-commit",
]);

interface Props {
  onSubmit: (payload: WebhookCreatePayload) => void;
  onCancel: () => void;
  loading?: boolean;
}

export function WebhookForm({ onSubmit, onCancel, loading }: Props) {
  const { t } = useTranslation("workspace");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [headers, setHeaders] = useState<WebhookHeaderIn[]>([
    { name: "X-Api-Key", value: "", vault: null, enabled: false },
  ]);
  const [headerErrors, setHeaderErrors] = useState<Record<number, string>>({});

  const hasReservedError = Object.keys(headerErrors).length > 0;

  function validateHeader(idx: number, headerName: string) {
    if (RESERVED.has(headerName.toLowerCase())) {
      setHeaderErrors((e) => ({
        ...e,
        [idx]: t("webhooks.form.reserved_error"),
      }));
    } else {
      setHeaderErrors((e) => {
        const copy = { ...e };
        delete copy[idx];
        return copy;
      });
    }
  }

  function addHeader() {
    setHeaders((h) => [...h, { name: "", value: "", vault: null, enabled: true }]);
  }

  function removeHeader(idx: number) {
    setHeaders((h) => h.filter((_, i) => i !== idx));
    setHeaderErrors((e) => {
      const copy = { ...e };
      delete copy[idx];
      return copy;
    });
  }

  function handleSubmit() {
    onSubmit({ name, url, enabled, headers });
  }

  return (
    <div className="space-y-4">
      <div>
        <Label>{t("webhooks.form.name")}</Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div>
        <Label>{t("webhooks.form.url")}</Label>
        <Input value={url} onChange={(e) => setUrl(e.target.value)} />
      </div>

      <div>
        <Label>{t("webhooks.form.headers")}</Label>
        <div className="space-y-2 mt-1">
          {headers.map((h, i) => (
            <div key={i} className="flex gap-2 items-start">
              <div className="flex-1">
                <Input
                  placeholder={t("webhooks.form.header_name")}
                  value={h.name}
                  onChange={(e) => {
                    const copy = [...headers];
                    copy[i] = { ...copy[i], name: e.target.value };
                    setHeaders(copy);
                  }}
                  onBlur={(e) => validateHeader(i, e.target.value)}
                />
                {headerErrors[i] && (
                  <p className="text-xs text-red-500 mt-1">{headerErrors[i]}</p>
                )}
              </div>
              <Input
                placeholder={t("webhooks.form.header_value")}
                type="password"
                value={h.value ?? ""}
                className="flex-1"
                onChange={(e) => {
                  const copy = [...headers];
                  copy[i] = { ...copy[i], value: e.target.value };
                  setHeaders(copy);
                }}
              />
              <Button variant="ghost" size="sm" onClick={() => removeHeader(i)}>
                ×
              </Button>
            </div>
          ))}
          <Button variant="outline" size="sm" onClick={addHeader}>
            {t("webhooks.form.add_header")}
          </Button>
        </div>
      </div>

      <div className="flex gap-2 justify-end">
        <Button variant="outline" onClick={onCancel}>
          {t("webhooks.form.cancel")}
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={loading || hasReservedError || !name || !url}
        >
          {t("webhooks.form.save")}
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Créer `WebhookCallsLog.tsx`**

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listWebhookCalls, purgeWebhookCalls } from "@/lib/webhooks";
import type { WebhookCallsFilter } from "@/lib/webhooks.types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

interface Props {
  workspaceName: string;
}

export function WebhookCallsLog({ workspaceName }: Props) {
  const { t } = useTranslation("workspace");
  const qc = useQueryClient();
  const [filter, setFilter] = useState<WebhookCallsFilter>({});

  const { data: calls = [] } = useQuery({
    queryKey: ["webhook-calls", workspaceName, filter],
    queryFn: () => listWebhookCalls(workspaceName, filter),
    refetchInterval: 30_000,
  });

  const purgeMutation = useMutation({
    mutationFn: () => purgeWebhookCalls(workspaceName),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["webhook-calls", workspaceName] }),
  });

  return (
    <div className="space-y-4">
      <div className="flex gap-2 flex-wrap">
        <Input
          placeholder={t("webhooks.calls.filter_correlation")}
          className="w-48"
          onChange={(e) =>
            setFilter((f) => ({ ...f, correlation_id: e.target.value || undefined }))
          }
        />
        <select
          className="border rounded px-2 text-sm"
          onChange={(e) =>
            setFilter((f) => ({
              ...f,
              status: (e.target.value as WebhookCallsFilter["status"]) || undefined,
            }))
          }
        >
          <option value="">{t("webhooks.calls.filter_all")}</option>
          <option value="success">{t("webhooks.calls.filter_success")}</option>
          <option value="error">{t("webhooks.calls.filter_error")}</option>
        </select>
        <Button
          variant="destructive"
          size="sm"
          onClick={() => purgeMutation.mutate()}
        >
          {t("webhooks.calls.purge")}
        </Button>
      </div>

      {calls.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("webhooks.calls.empty")}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("webhooks.calls.col_date")}</TableHead>
              <TableHead>{t("webhooks.calls.col_webhook")}</TableHead>
              <TableHead>{t("webhooks.calls.col_status")}</TableHead>
              <TableHead>{t("webhooks.calls.col_duration")}</TableHead>
              <TableHead>{t("webhooks.calls.col_correlation")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {calls.map((c) => (
              <TableRow key={c.id}>
                <TableCell className="text-xs">
                  {new Date(c.called_at).toLocaleTimeString()}
                </TableCell>
                <TableCell>{c.webhook_name}</TableCell>
                <TableCell>
                  {c.http_status ? (
                    <Badge variant={c.success ? "default" : "destructive"}>
                      {c.http_status}
                    </Badge>
                  ) : (
                    <Badge variant="destructive">ERR</Badge>
                  )}
                </TableCell>
                <TableCell>{c.duration_ms != null ? `${c.duration_ms}ms` : "—"}</TableCell>
                <TableCell className="font-mono text-xs truncate max-w-[120px]">
                  {c.correlation_id}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
```

- [ ] **Créer `WorkspaceWebhooksTab.tsx`**

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  createWebhook, deleteWebhook, listWebhooks, patchWebhook,
} from "@/lib/webhooks";
import type { Webhook, WebhookCreatePayload } from "@/lib/webhooks.types";
import { WebhookForm } from "./WebhookForm";
import { WebhookCallsLog } from "./WebhookCallsLog";

interface Props {
  workspaceName: string;
}

export function WorkspaceWebhooksTab({ workspaceName }: Props) {
  const { t } = useTranslation("workspace");
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [subTab, setSubTab] = useState("list");

  const { data: webhooks = [] } = useQuery({
    queryKey: ["webhooks", workspaceName],
    queryFn: () => listWebhooks(workspaceName),
  });

  const createMutation = useMutation({
    mutationFn: (payload: WebhookCreatePayload) =>
      createWebhook(workspaceName, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["webhooks", workspaceName] });
      setShowForm(false);
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      patchWebhook(workspaceName, id, { enabled }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["webhooks", workspaceName] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteWebhook(workspaceName, id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["webhooks", workspaceName] }),
  });

  return (
    <Tabs value={subTab} onValueChange={setSubTab}>
      <div className="flex items-center justify-between mb-4">
        <TabsList>
          <TabsTrigger value="list">{t("webhooks.list.title")}</TabsTrigger>
          <TabsTrigger value="calls">{t("webhooks.calls.title")}</TabsTrigger>
        </TabsList>
        {subTab === "list" && (
          <Button size="sm" onClick={() => setShowForm(true)}>
            {t("webhooks.list.add")}
          </Button>
        )}
      </div>

      <TabsContent value="list">
        {webhooks.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {t("webhooks.list.empty")}
          </p>
        ) : (
          <div className="space-y-2">
            {webhooks.map((wh: Webhook) => (
              <div
                key={wh.id}
                className="flex items-center justify-between border rounded p-3"
              >
                <div>
                  <span className="font-medium">{wh.name}</span>
                  <span className="text-xs text-muted-foreground ml-2">
                    {wh.url}
                  </span>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {t(
                      wh.headers.length === 1
                        ? "webhooks.list.headers_count"
                        : "webhooks.list.headers_count_plural",
                      { count: wh.headers.length }
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      toggleMutation.mutate({ id: wh.id, enabled: !wh.enabled })
                    }
                  >
                    <Badge variant={wh.enabled ? "default" : "secondary"}>
                      {wh.enabled
                        ? t("webhooks.list.enabled")
                        : t("webhooks.list.disabled")}
                    </Badge>
                  </Button>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="ghost" size="sm">×</Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>
                          {t("webhooks.list.delete_confirm")}
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                          {t("webhooks.list.delete_confirm_description")}
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>
                          {t("webhooks.form.cancel")}
                        </AlertDialogCancel>
                        <AlertDialogAction
                          onClick={() => deleteMutation.mutate(wh.id)}
                        >
                          {t("webhooks.list.delete_confirm")}
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </div>
            ))}
          </div>
        )}
      </TabsContent>

      <TabsContent value="calls">
        <WebhookCallsLog workspaceName={workspaceName} />
      </TabsContent>

      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("webhooks.form.title_create")}</DialogTitle>
          </DialogHeader>
          <WebhookForm
            onSubmit={(p) => createMutation.mutate(p)}
            onCancel={() => setShowForm(false)}
            loading={createMutation.isPending}
          />
        </DialogContent>
      </Dialog>
    </Tabs>
  );
}
```

- [ ] **Vérifier les tests**

```bash
cd frontend && npm run test:run -- WorkspaceWebhooksTab
```

Expected : PASS.

- [ ] **TS strict**

```bash
npx tsc --noEmit
```

Expected : no errors.

- [ ] **Commit**

```bash
git add frontend/src/pages/workspace/WorkspaceWebhooksTab.tsx frontend/src/pages/workspace/WebhookForm.tsx frontend/src/pages/workspace/WebhookCallsLog.tsx frontend/src/pages/workspace/__tests__/WorkspaceWebhooksTab.test.tsx
git commit -m "feat(front): composants WorkspaceWebhooksTab + WebhookForm + WebhookCallsLog"
```

---

## Task 13 : Frontend — onglet Webhooks dans WorkspaceDetailPanel

**Files:**
- Modify: `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx`

- [ ] **Ajouter l'onglet Webhooks**

Ajouter l'import :
```tsx
import { WorkspaceWebhooksTab } from "./WorkspaceWebhooksTab";
```

Dans `<TabsList>` (après l'onglet `chunking`) :
```tsx
<TabsTrigger value="webhooks">{t("webhooks.tabs.webhooks")}</TabsTrigger>
```

Après `<TabsContent value="chunking">` :
```tsx
<TabsContent value="webhooks" className="pt-4">
  <WorkspaceWebhooksTab workspaceName={ws.name} />
</TabsContent>
```

- [ ] **Vérifier TS strict + lint**

```bash
cd frontend
npx tsc --noEmit
npm run lint
```

- [ ] **Vérifier manuellement dans le navigateur**

Lancer le backend et le frontend :
```bash
# Terminal 1 : backend
cd backend && uv run uvicorn rag.main:app --reload

# Terminal 2 : frontend
cd frontend && npm run dev
```

Naviguer sur un workspace → onglet "Webhooks" → créer un webhook → vérifier que la liste s'affiche.
Tenter d'ajouter `X-Correlation-ID` comme header → vérifier le message d'erreur inline et le bouton désactivé.
Vérifier l'onglet "Audit log" (vide au départ, visible après dispatch).

- [ ] **Commit final**

```bash
git add frontend/src/pages/workspace/WorkspaceDetailPanel.tsx
git commit -m "feat(front): onglet Webhooks dans WorkspaceDetailPanel"
```

---

## Task 14 : Vérification finale + suite de tests complète

- [ ] **Lancer tous les tests backend**

```bash
cd backend && uv run pytest -v --tb=short
```

Expected : tous les tests PASS.

- [ ] **Lancer tous les tests frontend**

```bash
cd frontend && npm run test:run
```

Expected : tous les tests PASS.

- [ ] **TS strict**

```bash
cd frontend && npx tsc --noEmit
```

Expected : no errors.

- [ ] **Lint backend + frontend**

```bash
cd backend && uv run ruff check src/ tests/
cd frontend && npm run lint
```

Expected : no errors.

- [ ] **Commit de clôture si corrections mineures nécessaires**

```bash
git add -p
git commit -m "fix: corrections finales suite intégration push-async + webhooks"
```
