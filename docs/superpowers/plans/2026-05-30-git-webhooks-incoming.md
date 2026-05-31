# Git Webhooks Entrants — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recevoir les push events GitHub/GitLab/Gitea/Bitbucket/Azure DevOps et déclencher l'indexation RAG en mode réactif (`triggered_by='webhook'`), en remplacement du polling scheduler.

**Architecture:** Un endpoint public `POST /api/webhooks/git/{workspace_name}/{source_name}` valide la signature HMAC (ou token GitLab/Azure) via un strategy pattern par provider, extrait la branche du payload, et crée un `index_job` si la branche correspond. Trois endpoints admin gèrent l'activation, la désactivation et la rotation du secret (stocké dans Harpocrate). Le scheduler filtre `webhook_enabled = false` pour ignorer les sources pilotées par webhook.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, Harpocrate (secrets), pytest, React 18, TanStack Query, i18next, shadcn/ui.

---

## Contexte pour l'agent

- **Branche de travail :** `dev` — vérifier `git branch --show-current` avant tout edit.
- **Backend** : `backend/src/rag/`, tests dans `backend/tests/`.
- **Patterns à suivre :**
  - Migrations SQL numérotées dans `backend/migrations/` (prochain = `034_`)
  - JSONB config de source : champs lus/écrits via `json.loads(raw) if isinstance(raw, str) else dict(raw)` (cf. `services/sources.py::_source_to_dict`)
  - Secret résolu depuis Harpocrate via `resolver.resolve_with_retry(vault_ref)`
  - `_source_to_dict` retourne un `dict` depuis un `asyncpg.Record`
  - Tests unitaires purs (pas de DB) dans `backend/tests/unit/`
  - Tests API avec `httpx.AsyncClient` dans `backend/tests/api/`
  - `session_pool` + `run_migrations` pour les tests d'intégration (cf. conftest)
- **Frontend** : `frontend/src/`, i18n par namespace dans `src/i18n/fr/` et `src/i18n/en/`
- **RAG_PUBLIC_URL** : variable d'env exposée côté frontend via `import.meta.env.VITE_PUBLIC_URL` (ou construite depuis `window.location.origin` si absente — ne pas hardcoder)

---

## Task 1 — Migration DB : webhook_enabled

**Files:**
- Create: `backend/migrations/034_source_webhook_enabled.sql`
- Modify: `backend/src/rag/services/sources.py` (ajouter `webhook_enabled` dans `_source_to_dict` et le SELECT)
- Modify: `backend/src/rag/schemas/admin.py` (ajouter `webhook_enabled: bool` dans `SourceResponse`)

- [ ] **Step 1 : Créer la migration**

```sql
-- Migration 034 — webhook_enabled sur workspace_sources
ALTER TABLE workspace_sources
  ADD COLUMN webhook_enabled BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX idx_sources_webhook_enabled
  ON workspace_sources(webhook_enabled)
  WHERE webhook_enabled = true;
```

- [ ] **Step 2 : Mettre à jour `_source_to_dict` dans `services/sources.py`**

Modifier le SELECT `list_sources` pour inclure `webhook_enabled` :

```python
async def list_sources(config_pool: asyncpg.Pool, *, workspace_name: str) -> list[dict[str, Any]]:
    rows = await fetch_all(
        config_pool,
        """
        SELECT ws.id, ws.name, ws.type, ws.config, ws.last_indexed_at,
               ws.created_at, ws.webhook_enabled
        FROM workspace_sources ws
        JOIN workspaces w ON w.id = ws.workspace_id
        WHERE w.name = $1
        ORDER BY ws.created_at DESC
        """,
        workspace_name,
    )
    return [_source_to_dict(r) for r in rows]
```

Modifier `_source_to_dict` :

```python
def _source_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    raw_config = row["config"]
    config = json.loads(raw_config) if isinstance(raw_config, str) else dict(raw_config)
    last = row["last_indexed_at"]
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "type": row["type"],
        "config": config,
        "webhook_enabled": bool(row["webhook_enabled"]) if "webhook_enabled" in row.keys() else False,
        "last_indexed_at": last.isoformat() if last is not None else None,
        "created_at": row["created_at"].isoformat(),
    }
```

Même ajout dans `add_source` et `update_source` (RETURNING) :

```sql
RETURNING id, name, type, config, last_indexed_at, created_at, webhook_enabled
```

- [ ] **Step 3 : Mettre à jour `SourceResponse` dans `schemas/admin.py`**

```python
class SourceResponse(BaseModel):
    id: UUID
    name: str | None
    type: str
    config: dict[str, Any]
    webhook_enabled: bool = False
    last_indexed_at: str | None
    created_at: str
    branch_warning: str | None = None
```

- [ ] **Step 4 : Vérifier la migration s'applique**

```bash
cd backend && uv run python -m agflow.db.migrations
```

Expected : `Applied migration 034_source_webhook_enabled.sql`

- [ ] **Step 5 : Commit**

```bash
git add backend/migrations/034_source_webhook_enabled.sql \
        backend/src/rag/services/sources.py \
        backend/src/rag/schemas/admin.py
git commit -m "feat(db): migration 034 — webhook_enabled sur workspace_sources"
```

---

## Task 2 — Validateurs HMAC par provider

**Files:**
- Create: `backend/src/rag/sync/webhook_validators.py`
- Create: `backend/tests/unit/test_webhook_validators.py`

- [ ] **Step 1 : Écrire les tests (rouge)**

```python
# backend/tests/unit/test_webhook_validators.py
from __future__ import annotations

import hashlib
import hmac
import base64

import pytest

from rag.sync.webhook_validators import validate


PAYLOAD = b'{"ref":"refs/heads/main"}'
SECRET = "mysecret"


# ── GitHub ──────────────────────────────────────────────────────────────────

def _github_sig(payload: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), payload, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def test_github_valid() -> None:
    headers = {"x-hub-signature-256": _github_sig(PAYLOAD, SECRET)}
    assert validate("github", SECRET, headers, PAYLOAD) is True


def test_github_invalid_sig() -> None:
    headers = {"x-hub-signature-256": "sha256=badbad"}
    assert validate("github", SECRET, headers, PAYLOAD) is False


def test_github_missing_header() -> None:
    assert validate("github", SECRET, {}, PAYLOAD) is False


# ── Gitea ────────────────────────────────────────────────────────────────────

def _gitea_sig(payload: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), payload, hashlib.sha256)
    return mac.hexdigest()


def test_gitea_valid() -> None:
    headers = {"x-gitea-signature": _gitea_sig(PAYLOAD, SECRET)}
    assert validate("gitea", SECRET, headers, PAYLOAD) is True


def test_gitea_invalid() -> None:
    headers = {"x-gitea-signature": "badhex"}
    assert validate("gitea", SECRET, headers, PAYLOAD) is False


# ── GitLab ───────────────────────────────────────────────────────────────────

def test_gitlab_valid() -> None:
    headers = {"x-gitlab-token": SECRET}
    assert validate("gitlab", SECRET, headers, PAYLOAD) is True


def test_gitlab_invalid() -> None:
    headers = {"x-gitlab-token": "wrongtoken"}
    assert validate("gitlab", SECRET, headers, PAYLOAD) is False


def test_gitlab_missing() -> None:
    assert validate("gitlab", SECRET, {}, PAYLOAD) is False


# ── Bitbucket ────────────────────────────────────────────────────────────────

def _bitbucket_sig(payload: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), payload, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def test_bitbucket_valid() -> None:
    headers = {"x-hub-signature": _bitbucket_sig(PAYLOAD, SECRET)}
    assert validate("bitbucket", SECRET, headers, PAYLOAD) is True


def test_bitbucket_invalid() -> None:
    headers = {"x-hub-signature": "sha256=bad"}
    assert validate("bitbucket", SECRET, headers, PAYLOAD) is False


# ── Azure DevOps ─────────────────────────────────────────────────────────────

def _azure_basic(secret: str) -> str:
    return "Basic " + base64.b64encode(f":{secret}".encode()).decode()


def test_azure_valid() -> None:
    headers = {"authorization": _azure_basic(SECRET)}
    assert validate("azure-devops", SECRET, headers, PAYLOAD) is True


def test_azure_invalid() -> None:
    headers = {"authorization": "Basic " + base64.b64encode(b":wrong").decode()}
    assert validate("azure-devops", SECRET, headers, PAYLOAD) is False


def test_azure_missing() -> None:
    assert validate("azure-devops", SECRET, {}, PAYLOAD) is False


# ── Provider inconnu ─────────────────────────────────────────────────────────

def test_unknown_provider_returns_false() -> None:
    assert validate("unknown", SECRET, {}, PAYLOAD) is False
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_webhook_validators.py -v
```

Expected : `ImportError` ou `ModuleNotFoundError`

- [ ] **Step 3 : Implémenter `webhook_validators.py`**

```python
# backend/src/rag/sync/webhook_validators.py
from __future__ import annotations

import base64
import hashlib
import hmac


def validate(
    provider: str,
    secret: str,
    headers: dict[str, str],
    raw_body: bytes,
) -> bool:
    """Valide la signature d'un webhook entrant selon le provider git.

    `headers` doit avoir des clés en minuscules.
    Retourne False pour tout provider inconnu ou header manquant.
    """
    match provider:
        case "github":
            return _validate_hmac_sha256(
                secret, raw_body, headers.get("x-hub-signature-256", ""), prefix="sha256="
            )
        case "gitea":
            return _validate_hmac_sha256(
                secret, raw_body, headers.get("x-gitea-signature", ""), prefix=""
            )
        case "gitlab":
            token = headers.get("x-gitlab-token", "")
            return hmac.compare_digest(token.encode(), secret.encode())
        case "bitbucket":
            return _validate_hmac_sha256(
                secret, raw_body, headers.get("x-hub-signature", ""), prefix="sha256="
            )
        case "azure-devops":
            return _validate_azure_basic(secret, headers.get("authorization", ""))
        case _:
            return False


def _validate_hmac_sha256(secret: str, body: bytes, header_value: str, prefix: str) -> bool:
    if not header_value:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    actual = header_value.removeprefix(prefix)
    return hmac.compare_digest(expected, actual)


def _validate_azure_basic(secret: str, auth_header: str) -> bool:
    if not auth_header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth_header[6:]).decode()
    except Exception:
        return False
    password = decoded.split(":", 1)[-1]
    return hmac.compare_digest(password.encode(), secret.encode())
```

- [ ] **Step 4 : Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_webhook_validators.py -v
```

Expected : `17 passed`

- [ ] **Step 5 : Commit**

```bash
git add backend/src/rag/sync/webhook_validators.py \
        backend/tests/unit/test_webhook_validators.py
git commit -m "feat(sync): webhook_validators — HMAC par provider (github/gitea/gitlab/bitbucket/azure)"
```

---

## Task 3 — Parseurs de branche par provider

**Files:**
- Create: `backend/src/rag/sync/webhook_parsers.py`
- Create: `backend/tests/unit/test_webhook_parsers.py`

- [ ] **Step 1 : Écrire les tests (rouge)**

```python
# backend/tests/unit/test_webhook_parsers.py
from __future__ import annotations

import pytest

from rag.sync.webhook_parsers import extract_branch


def test_github_push_ref() -> None:
    payload = {"ref": "refs/heads/main"}
    assert extract_branch("github", payload) == "main"


def test_github_tag_ref_returns_none() -> None:
    payload = {"ref": "refs/tags/v1.0"}
    assert extract_branch("github", payload) is None


def test_github_missing_ref() -> None:
    assert extract_branch("github", {}) is None


def test_gitea_same_as_github() -> None:
    payload = {"ref": "refs/heads/dev"}
    assert extract_branch("gitea", payload) == "dev"


def test_gitlab_same_as_github() -> None:
    payload = {"ref": "refs/heads/feature-x"}
    assert extract_branch("gitlab", payload) == "feature-x"


def test_bitbucket_push_new_name() -> None:
    payload = {"push": {"changes": [{"new": {"name": "main"}}]}}
    assert extract_branch("bitbucket", payload) == "main"


def test_bitbucket_missing_changes_returns_none() -> None:
    assert extract_branch("bitbucket", {"push": {"changes": []}}) is None


def test_bitbucket_no_push_key_returns_none() -> None:
    assert extract_branch("bitbucket", {}) is None


def test_azure_devops_ref_updates() -> None:
    payload = {
        "resource": {
            "refUpdates": [{"name": "refs/heads/main"}]
        }
    }
    assert extract_branch("azure-devops", payload) == "main"


def test_azure_devops_tag_returns_none() -> None:
    payload = {
        "resource": {
            "refUpdates": [{"name": "refs/tags/v1"}]
        }
    }
    assert extract_branch("azure-devops", payload) is None


def test_azure_devops_missing_returns_none() -> None:
    assert extract_branch("azure-devops", {}) is None


def test_unknown_provider_returns_none() -> None:
    assert extract_branch("unknown", {"ref": "refs/heads/main"}) is None
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_webhook_parsers.py -v
```

Expected : `ImportError`

- [ ] **Step 3 : Implémenter `webhook_parsers.py`**

```python
# backend/src/rag/sync/webhook_parsers.py
from __future__ import annotations

from typing import Any

_HEADS_PREFIX = "refs/heads/"


def extract_branch(provider: str, payload: dict[str, Any]) -> str | None:
    """Extrait le nom de branche depuis un payload de push webhook.

    Retourne None si le payload n'est pas un push sur une branche
    (ex: tag, ping, event non-push) ou si le provider est inconnu.
    """
    match provider:
        case "github" | "gitea" | "gitlab":
            return _from_ref(payload.get("ref", ""))
        case "bitbucket":
            return _from_bitbucket(payload)
        case "azure-devops":
            return _from_azure(payload)
        case _:
            return None


def _from_ref(ref: str) -> str | None:
    if ref.startswith(_HEADS_PREFIX):
        return ref[len(_HEADS_PREFIX):]
    return None


def _from_bitbucket(payload: dict[str, Any]) -> str | None:
    try:
        changes: list[Any] = payload["push"]["changes"]
        if not changes:
            return None
        return str(changes[0]["new"]["name"])
    except (KeyError, IndexError, TypeError):
        return None


def _from_azure(payload: dict[str, Any]) -> str | None:
    try:
        updates: list[Any] = payload["resource"]["refUpdates"]
        if not updates:
            return None
        return _from_ref(str(updates[0]["name"]))
    except (KeyError, IndexError, TypeError):
        return None
```

- [ ] **Step 4 : Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_webhook_parsers.py -v
```

Expected : `12 passed`

- [ ] **Step 5 : Commit**

```bash
git add backend/src/rag/sync/webhook_parsers.py \
        backend/tests/unit/test_webhook_parsers.py
git commit -m "feat(sync): webhook_parsers — extract_branch par provider"
```

---

## Task 4 — Service source_webhooks (enable/disable/rotate)

**Files:**
- Create: `backend/src/rag/services/source_webhooks.py`
- Create: `backend/tests/unit/test_source_webhooks.py`

- [ ] **Step 1 : Écrire les tests (rouge)**

```python
# backend/tests/unit/test_source_webhooks.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from rag.services.source_webhooks import (
    WebhookAlreadyEnabled,
    WebhookNotEnabled,
    _build_harpo_path,
    _build_vault_ref,
)


def test_build_harpo_path() -> None:
    assert _build_harpo_path("myws", "my-repo") == "sources/myws/my-repo/webhook_secret"


def test_build_vault_ref() -> None:
    ref = _build_vault_ref("vault1", "myws", "my-repo")
    assert ref == "${vault://vault1:/sources/myws/my-repo/webhook_secret}"


def test_webhook_already_enabled_is_exception() -> None:
    exc = WebhookAlreadyEnabled("myws", "repo")
    assert "myws" in str(exc)


def test_webhook_not_enabled_is_exception() -> None:
    exc = WebhookNotEnabled("myws", "repo")
    assert "repo" in str(exc)
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_source_webhooks.py -v
```

Expected : `ImportError`

- [ ] **Step 3 : Implémenter `source_webhooks.py`**

```python
# backend/src/rag/services/source_webhooks.py
from __future__ import annotations

import json
import secrets
from typing import Any, Protocol

import asyncpg
import structlog

from rag.db.helpers import fetch_one

log = structlog.get_logger(__name__)

_VAULT_REF_TMPL = "${vault://%s:/%s}"


class _VaultSvc(Protocol):
    async def get_by_name(self, conn: asyncpg.Connection, name: str) -> Any | None: ...


class _ClientProvider(Protocol):
    async def get_client(self, key: str) -> Any: ...
    async def get_default_vault_name(self) -> str | None: ...


class WebhookAlreadyEnabled(Exception):
    def __init__(self, workspace: str, source: str) -> None:
        super().__init__(f"Webhook already enabled on {workspace}/{source}")


class WebhookNotEnabled(Exception):
    def __init__(self, workspace: str, source: str) -> None:
        super().__init__(f"Webhook not enabled on {workspace}/{source}")


def _build_harpo_path(workspace_name: str, source_name: str) -> str:
    return f"sources/{workspace_name}/{source_name}/webhook_secret"


def _build_vault_ref(vault_name: str, workspace_name: str, source_name: str) -> str:
    path = _build_harpo_path(workspace_name, source_name)
    return _VAULT_REF_TMPL % (vault_name, path)


async def enable_webhook(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    source_name: str,
    vault_svc: _VaultSvc,
    client_provider: _ClientProvider,
) -> str:
    """Active le mode webhook sur la source. Retourne le secret en clair (une seule fois).

    Lève WebhookAlreadyEnabled si webhook_enabled = true.
    """
    row = await fetch_one(
        conn,
        """
        SELECT ws.id, ws.config, ws.webhook_enabled
        FROM workspace_sources ws
        JOIN workspaces w ON w.id = ws.workspace_id
        WHERE w.name = $1 AND ws.name = $2
        """,
        workspace_name,
        source_name,
    )
    if row is None:
        raise ValueError(f"Source {source_name!r} not found in workspace {workspace_name!r}")
    if row["webhook_enabled"]:
        raise WebhookAlreadyEnabled(workspace_name, source_name)

    vault_name = await client_provider.get_default_vault_name()
    if vault_name is None:
        raise RuntimeError("No default Harpocrate vault configured")

    vault = await vault_svc.get_by_name(conn, vault_name)
    if vault is None:
        raise RuntimeError(f"Vault {vault_name!r} not found")

    secret = secrets.token_hex(32)
    harpo_path = _build_harpo_path(workspace_name, source_name)
    client = await client_provider.get_client(str(vault.api_key_id))
    await __import__("asyncio").to_thread(client.set_secret, harpo_path, secret)

    vault_ref = _build_vault_ref(vault_name, workspace_name, source_name)

    raw = row["config"]
    config = json.loads(raw) if isinstance(raw, str) else dict(raw)
    config["webhook_secret_ref"] = vault_ref

    await conn.execute(
        """
        UPDATE workspace_sources
        SET config = $1::jsonb,
            webhook_enabled = true,
            next_sync_at = NULL
        WHERE id = $2
        """,
        json.dumps(config),
        row["id"],
    )
    log.info("source.webhook.enabled", workspace=workspace_name, source=source_name)
    return secret


async def disable_webhook(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    source_name: str,
    vault_svc: _VaultSvc,
    client_provider: _ClientProvider,
) -> None:
    """Désactive le mode webhook. Supprime le secret dans Harpocrate et relance le scheduler."""
    row = await fetch_one(
        conn,
        """
        SELECT ws.id, ws.config, ws.webhook_enabled
        FROM workspace_sources ws
        JOIN workspaces w ON w.id = ws.workspace_id
        WHERE w.name = $1 AND ws.name = $2
        """,
        workspace_name,
        source_name,
    )
    if row is None:
        raise ValueError(f"Source {source_name!r} not found in workspace {workspace_name!r}")
    if not row["webhook_enabled"]:
        raise WebhookNotEnabled(workspace_name, source_name)

    raw = row["config"]
    config = json.loads(raw) if isinstance(raw, str) else dict(raw)

    vault_ref: str | None = config.pop("webhook_secret_ref", None)
    if vault_ref:
        vault_name = await client_provider.get_default_vault_name()
        if vault_name:
            vault = await vault_svc.get_by_name(conn, vault_name)
            if vault:
                harpo_path = _build_harpo_path(workspace_name, source_name)
                client = await client_provider.get_client(str(vault.api_key_id))
                try:
                    await __import__("asyncio").to_thread(client.delete_secret, harpo_path)
                except Exception:
                    log.warning("source.webhook.delete_secret_failed", path=harpo_path)

    await conn.execute(
        """
        UPDATE workspace_sources
        SET config = $1::jsonb,
            webhook_enabled = false,
            next_sync_at = now()
        WHERE id = $2
        """,
        json.dumps(config),
        row["id"],
    )
    log.info("source.webhook.disabled", workspace=workspace_name, source=source_name)


async def rotate_webhook_secret(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    source_name: str,
    vault_svc: _VaultSvc,
    client_provider: _ClientProvider,
) -> str:
    """Génère un nouveau secret et l'écrase dans Harpocrate. Retourne le secret en clair."""
    row = await fetch_one(
        conn,
        """
        SELECT ws.id, ws.config, ws.webhook_enabled
        FROM workspace_sources ws
        JOIN workspaces w ON w.id = ws.workspace_id
        WHERE w.name = $1 AND ws.name = $2
        """,
        workspace_name,
        source_name,
    )
    if row is None:
        raise ValueError(f"Source {source_name!r} not found in workspace {workspace_name!r}")
    if not row["webhook_enabled"]:
        raise WebhookNotEnabled(workspace_name, source_name)

    vault_name = await client_provider.get_default_vault_name()
    if vault_name is None:
        raise RuntimeError("No default Harpocrate vault configured")
    vault = await vault_svc.get_by_name(conn, vault_name)
    if vault is None:
        raise RuntimeError(f"Vault {vault_name!r} not found")

    new_secret = secrets.token_hex(32)
    harpo_path = _build_harpo_path(workspace_name, source_name)
    client = await client_provider.get_client(str(vault.api_key_id))
    await __import__("asyncio").to_thread(client.set_secret, harpo_path, new_secret)

    log.info("source.webhook.secret_rotated", workspace=workspace_name, source=source_name)
    return new_secret
```

- [ ] **Step 4 : Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_source_webhooks.py -v
```

Expected : `4 passed`

- [ ] **Step 5 : Commit**

```bash
git add backend/src/rag/services/source_webhooks.py \
        backend/tests/unit/test_source_webhooks.py
git commit -m "feat(services): source_webhooks — enable/disable/rotate_secret"
```

---

## Task 5 — Endpoint entrant POST /api/webhooks/git/{workspace}/{source}

**Files:**
- Create: `backend/src/rag/api/git_webhooks.py`
- Modify: `backend/src/rag/main.py` (include_router)
- Create: `backend/tests/unit/test_git_webhooks_endpoint.py`

- [ ] **Step 1 : Écrire les tests (rouge)**

```python
# backend/tests/unit/test_git_webhooks_endpoint.py
from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from rag.api.git_webhooks import build_git_webhooks_router


def _make_app(source_row: dict | None, config_row: dict | None = None) -> FastAPI:
    app = FastAPI()
    app.state.pools = MagicMock()

    async def fake_fetchrow(*args, **kwargs):
        return source_row

    pool_mock = AsyncMock()
    pool_mock.acquire.return_value.__aenter__ = AsyncMock(return_value=pool_mock)
    pool_mock.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    pool_mock.fetchrow = AsyncMock(side_effect=fake_fetchrow)
    pool_mock.execute = AsyncMock()
    app.state.pools.config_pool = pool_mock

    resolver_mock = MagicMock()
    resolver_mock.resolve_with_retry = AsyncMock(return_value="mysecret")
    app.state.resolver = resolver_mock

    app.include_router(build_git_webhooks_router())
    return app


PAYLOAD = json.dumps({"ref": "refs/heads/main"}).encode()
SECRET = "mysecret"


def _github_sig(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_webhook_404_when_source_not_found() -> None:
    app = _make_app(source_row=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/webhooks/git/myws/myrepo",
            content=PAYLOAD,
            headers={"x-hub-signature-256": _github_sig(PAYLOAD, SECRET)},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_webhook_404_when_not_enabled() -> None:
    source = {
        "id": "uuid-1",
        "webhook_enabled": False,
        "config": json.dumps({"git_provider": "github", "branch": "main",
                              "webhook_secret_ref": "${vault://v:/p}"}),
    }
    app = _make_app(source_row=source)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/webhooks/git/myws/myrepo",
            content=PAYLOAD,
            headers={"x-hub-signature-256": _github_sig(PAYLOAD, SECRET)},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_webhook_401_invalid_signature() -> None:
    source = {
        "id": "uuid-1",
        "webhook_enabled": True,
        "config": json.dumps({"git_provider": "github", "branch": "main",
                              "webhook_secret_ref": "${vault://v:/p}"}),
    }
    app = _make_app(source_row=source)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/webhooks/git/myws/myrepo",
            content=PAYLOAD,
            headers={"x-hub-signature-256": "sha256=bad"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_200_wrong_branch_silent() -> None:
    source = {
        "id": "uuid-1",
        "webhook_enabled": True,
        "config": json.dumps({"git_provider": "github", "branch": "main",
                              "webhook_secret_ref": "${vault://v:/p}"}),
    }
    app = _make_app(source_row=source)
    payload = json.dumps({"ref": "refs/heads/other"}).encode()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/webhooks/git/myws/myrepo",
            content=payload,
            headers={"x-hub-signature-256": _github_sig(payload, SECRET)},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_git_webhooks_endpoint.py -v
```

Expected : `ImportError`

- [ ] **Step 3 : Implémenter `git_webhooks.py`**

```python
# backend/src/rag/api/git_webhooks.py
from __future__ import annotations

import json

import asyncpg
import structlog
from fastapi import APIRouter, HTTPException, Request, Response, status

from rag.sync.webhook_parsers import extract_branch
from rag.sync.webhook_validators import validate

log = structlog.get_logger(__name__)


def build_git_webhooks_router() -> APIRouter:
    router = APIRouter(tags=["git-webhooks"])

    @router.post(
        "/api/webhooks/git/{workspace_name}/{source_name}",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def receive_git_push(
        workspace_name: str,
        source_name: str,
        request: Request,
    ) -> dict:
        pool: asyncpg.Pool = request.app.state.pools.config_pool
        resolver = request.app.state.resolver

        raw_body = await request.body()

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT ws.id AS source_id, ws.config, ws.webhook_enabled,
                       w.id AS workspace_id
                FROM workspace_sources ws
                JOIN workspaces w ON w.id = ws.workspace_id
                WHERE w.name = $1 AND ws.name = $2
                """,
                workspace_name,
                source_name,
            )

        if row is None or not row["webhook_enabled"]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source not found")

        raw = row["config"]
        config = json.loads(raw) if isinstance(raw, str) else dict(raw)

        secret_ref: str | None = config.get("webhook_secret_ref")
        if not secret_ref:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="webhook_secret_ref missing",
            )

        secret = await resolver.resolve_with_retry(secret_ref)

        headers_lower = {k.lower(): v for k, v in request.headers.items()}
        provider: str = config.get("git_provider", "github")

        if not validate(provider, secret, headers_lower, raw_body):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature"
            )

        payload = json.loads(raw_body)
        pushed_branch = extract_branch(provider, payload)
        expected_branch: str = config.get("webhook_branch_filter") or config.get("branch", "main")

        if pushed_branch != expected_branch:
            log.info(
                "git_webhook.branch_mismatch",
                workspace=workspace_name,
                source=source_name,
                pushed=pushed_branch,
                expected=expected_branch,
            )
            return {"status": "ignored", "reason": "branch_mismatch"}

        async with pool.acquire() as conn:
            job_row = await conn.fetchrow(
                """
                INSERT INTO index_jobs (workspace_id, source_id, triggered_by, status)
                VALUES ($1, $2, 'webhook', 'pending')
                RETURNING id
                """,
                row["workspace_id"],
                row["source_id"],
            )

        job_id = str(job_row["id"])
        log.info(
            "git_webhook.job_created",
            workspace=workspace_name,
            source=source_name,
            job_id=job_id,
        )
        return {"status": "pending", "job_id": job_id}

    return router
```

- [ ] **Step 4 : Enregistrer le router dans `main.py`**

Ajouter en haut du fichier :
```python
from rag.api.git_webhooks import build_git_webhooks_router
```

Dans `_register_routers` (après `include_router(build_mcp_router())`):
```python
app.include_router(build_git_webhooks_router())
```

- [ ] **Step 5 : Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_git_webhooks_endpoint.py -v
```

Expected : `4 passed`

- [ ] **Step 6 : Commit**

```bash
git add backend/src/rag/api/git_webhooks.py \
        backend/src/rag/main.py \
        backend/tests/unit/test_git_webhooks_endpoint.py
git commit -m "feat(api): endpoint POST /api/webhooks/git/{workspace}/{source}"
```

---

## Task 6 — API admin : enable/disable/rotate-secret

**Files:**
- Modify: `backend/src/rag/api/admin.py` (3 nouveaux endpoints dans `build_admin_router`)
- Modify: `backend/src/rag/schemas/admin.py` (WebhookEnableResponse)
- Create: `backend/tests/unit/test_admin_source_webhook.py`

- [ ] **Step 1 : Ajouter `WebhookEnableResponse` dans `schemas/admin.py`**

```python
class WebhookEnableResponse(BaseModel):
    """Retour de POST /workspaces/{name}/sources/{source}/webhook/enable."""
    source_name: str
    webhook_url: str
    secret: str  # en clair, une seule fois
```

- [ ] **Step 2 : Écrire les tests (rouge)**

```python
# backend/tests/unit/test_admin_source_webhook.py
from __future__ import annotations

import pytest

from rag.schemas.admin import WebhookEnableResponse


def test_webhook_enable_response_fields() -> None:
    r = WebhookEnableResponse(
        source_name="my-repo",
        webhook_url="https://rag.example.com/api/webhooks/git/ws1/my-repo",
        secret="abc123",
    )
    assert r.source_name == "my-repo"
    assert "my-repo" in r.webhook_url
    assert r.secret == "abc123"
```

- [ ] **Step 3 : Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_admin_source_webhook.py -v
```

Expected : `ImportError` sur `WebhookEnableResponse`

- [ ] **Step 4 : Ajouter les 3 endpoints dans `admin.py`**

À l'intérieur de `build_admin_router()`, après les endpoints sources existants, ajouter :

```python
    @router.post(
        "/workspaces/{name}/sources/{source_name}/webhook/enable",
        response_model=WebhookEnableResponse,
    )
    async def enable_source_webhook(
        name: str, source_name: str, request: Request
    ) -> WebhookEnableResponse:
        from rag.services.source_webhooks import WebhookAlreadyEnabled, enable_webhook
        try:
            async with _config_pool(request).acquire() as conn:
                secret = await enable_webhook(
                    conn,
                    workspace_name=name,
                    source_name=source_name,
                    vault_svc=request.app.state.harpocrate_vaults_service,
                    client_provider=request.app.state.client_provider,
                )
        except WebhookAlreadyEnabled as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        public_url = str(request.app.state.settings.rag_public_url).rstrip("/")
        webhook_url = f"{public_url}/api/webhooks/git/{name}/{source_name}"
        return WebhookEnableResponse(
            source_name=source_name,
            webhook_url=webhook_url,
            secret=secret,
        )

    @router.post(
        "/workspaces/{name}/sources/{source_name}/webhook/disable",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def disable_source_webhook(
        name: str, source_name: str, request: Request
    ) -> Response:
        from rag.services.source_webhooks import WebhookNotEnabled, disable_webhook
        try:
            async with _config_pool(request).acquire() as conn:
                await disable_webhook(
                    conn,
                    workspace_name=name,
                    source_name=source_name,
                    vault_svc=request.app.state.harpocrate_vaults_service,
                    client_provider=request.app.state.client_provider,
                )
        except WebhookNotEnabled as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post(
        "/workspaces/{name}/sources/{source_name}/webhook/rotate-secret",
    )
    async def rotate_source_webhook_secret(
        name: str, source_name: str, request: Request
    ) -> dict:
        from rag.services.source_webhooks import WebhookNotEnabled, rotate_webhook_secret
        try:
            async with _config_pool(request).acquire() as conn:
                new_secret = await rotate_webhook_secret(
                    conn,
                    workspace_name=name,
                    source_name=source_name,
                    vault_svc=request.app.state.harpocrate_vaults_service,
                    client_provider=request.app.state.client_provider,
                )
        except WebhookNotEnabled as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        return {"secret": new_secret}
```

Ajouter l'import dans les imports du fichier :
```python
from rag.schemas.admin import (
    ...
    WebhookEnableResponse,
)
```

- [ ] **Step 5 : Vérifier que les tests passent + lint**

```bash
cd backend && uv run pytest tests/unit/test_admin_source_webhook.py -v
cd backend && uv run ruff check src/ tests/
```

Expected : `1 passed`, 0 erreurs lint

- [ ] **Step 6 : Commit**

```bash
git add backend/src/rag/api/admin.py \
        backend/src/rag/schemas/admin.py \
        backend/tests/unit/test_admin_source_webhook.py
git commit -m "feat(api): endpoints admin enable/disable/rotate-secret webhook source"
```

---

## Task 7 — Scheduler : filtre webhook_enabled

**Files:**
- Modify: `backend/src/rag/sync/scheduler.py`
- Create: `backend/tests/unit/test_scheduler_webhook_filter.py`

- [ ] **Step 1 : Écrire le test (rouge)**

```python
# backend/tests/unit/test_scheduler_webhook_filter.py
from __future__ import annotations

import re
import pytest

from rag.sync.scheduler import schedule_due_sources


def test_scheduler_query_excludes_webhook_enabled() -> None:
    """Le SQL de schedule_due_sources doit contenir webhook_enabled = false."""
    import inspect
    src = inspect.getsource(schedule_due_sources)
    assert "webhook_enabled" in src
    assert "false" in src.lower()
```

- [ ] **Step 2 : Vérifier que le test échoue**

```bash
cd backend && uv run pytest tests/unit/test_scheduler_webhook_filter.py -v
```

Expected : `FAILED` (webhook_enabled absent du source)

- [ ] **Step 3 : Modifier `scheduler.py`**

Dans `schedule_due_sources`, modifier le WHERE :

```python
        due = await conn.fetch(
            """
            SELECT s.id AS source_id, s.workspace_id, s.config
            FROM workspace_sources s
            WHERE s.next_sync_at IS NOT NULL
              AND s.next_sync_at <= now()
              AND s.webhook_enabled = false
              AND NOT EXISTS (
                  SELECT 1 FROM index_jobs j
                  WHERE j.source_id = s.id
                    AND j.status IN ('pending', 'running')
              )
            ORDER BY s.next_sync_at
            LIMIT 100
            FOR UPDATE SKIP LOCKED
            """
        )
```

- [ ] **Step 4 : Vérifier que le test passe**

```bash
cd backend && uv run pytest tests/unit/test_scheduler_webhook_filter.py -v
```

Expected : `1 passed`

- [ ] **Step 5 : Commit**

```bash
git add backend/src/rag/sync/scheduler.py \
        backend/tests/unit/test_scheduler_webhook_filter.py
git commit -m "feat(sync): scheduler ignore les sources webhook_enabled=true"
```

---

## Task 8 — Frontend : types + API + hooks + i18n

**Files:**
- Create: `frontend/src/lib/source-webhooks.types.ts`
- Create: `frontend/src/lib/source-webhooks.ts`
- Create: `frontend/src/hooks/useSourceWebhooks.ts`
- Create: `frontend/src/i18n/fr/git_webhooks.json`
- Create: `frontend/src/i18n/en/git_webhooks.json`
- Modify: `frontend/src/i18n/fr/sources.json` (ajouter `webhook_badge_on` / `webhook_badge_off` si absent)
- Modify: `frontend/src/lib/workspaces.types.ts` (ajouter `webhook_enabled` sur Source)

- [ ] **Step 1 : Mettre à jour le type `Source` dans `workspaces.types.ts`**

Trouver la définition de `Source` (ou type équivalent pour les sources) et ajouter :
```typescript
webhook_enabled: boolean;
```

- [ ] **Step 2 : Créer `source-webhooks.types.ts`**

```typescript
// frontend/src/lib/source-webhooks.types.ts

export interface WebhookEnableResponse {
  source_name: string;
  webhook_url: string;
  secret: string;
}

export interface WebhookRotateResponse {
  secret: string;
}
```

- [ ] **Step 3 : Créer `source-webhooks.ts`**

```typescript
// frontend/src/lib/source-webhooks.ts
import { apiFetch } from "./api";
import type { WebhookEnableResponse, WebhookRotateResponse } from "./source-webhooks.types";

const base = (workspace: string, source: string) =>
  `/api/admin/workspaces/${workspace}/sources/${source}/webhook`;

export const sourceWebhooksApi = {
  enable: (workspace: string, source: string): Promise<WebhookEnableResponse> =>
    apiFetch<WebhookEnableResponse>(`${base(workspace, source)}/enable`, { method: "POST" }),

  disable: (workspace: string, source: string): Promise<void> =>
    apiFetch<void>(`${base(workspace, source)}/disable`, { method: "POST" }),

  rotateSecret: (workspace: string, source: string): Promise<WebhookRotateResponse> =>
    apiFetch<WebhookRotateResponse>(`${base(workspace, source)}/rotate-secret`, {
      method: "POST",
    }),
};
```

- [ ] **Step 4 : Créer `useSourceWebhooks.ts`**

```typescript
// frontend/src/hooks/useSourceWebhooks.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { sourceWebhooksApi } from "@/lib/source-webhooks";

export function useEnableWebhook(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sourceName: string) =>
      sourceWebhooksApi.enable(workspaceName, sourceName),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["sources", workspaceName] });
    },
  });
}

export function useDisableWebhook(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sourceName: string) =>
      sourceWebhooksApi.disable(workspaceName, sourceName),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["sources", workspaceName] });
    },
  });
}

export function useRotateWebhookSecret(workspaceName: string) {
  return useMutation({
    mutationFn: (sourceName: string) =>
      sourceWebhooksApi.rotateSecret(workspaceName, sourceName),
  });
}
```

- [ ] **Step 5 : Créer les fichiers i18n**

`frontend/src/i18n/fr/git_webhooks.json` :
```json
{
  "enable_dialog_title": "Activer le webhook",
  "url_label": "URL à configurer dans votre provider git",
  "secret_label": "Secret généré (copiez-le maintenant)",
  "secret_warning": "Ce secret ne sera plus affiché après fermeture.",
  "content_type_hint": "Content type : application/json — Événements : Push events uniquement",
  "confirm": "Confirmer",
  "cancel": "Annuler",
  "close": "Fermer",
  "copied_toast": "Copié dans le presse-papiers",
  "enable_error": "Erreur lors de l'activation du webhook",
  "disable_confirm_title": "Désactiver le webhook ?",
  "disable_confirm_body": "La source repassera en mode polling (schedule). L'ancien secret sera supprimé.",
  "disable_btn": "Désactiver",
  "disable_error": "Erreur lors de la désactivation",
  "rotate_dialog_title": "Rotation du secret",
  "rotate_new_secret_label": "Nouveau secret (copiez-le maintenant)",
  "rotate_error": "Erreur lors de la rotation du secret",
  "badge_webhook": "Webhook",
  "badge_schedule": "Schedule",
  "menu_enable": "Activer le webhook",
  "menu_rotate": "Rotation du secret",
  "menu_disable": "Désactiver le webhook"
}
```

`frontend/src/i18n/en/git_webhooks.json` :
```json
{
  "enable_dialog_title": "Enable webhook",
  "url_label": "URL to configure in your git provider",
  "secret_label": "Generated secret (copy it now)",
  "secret_warning": "This secret will not be shown again after closing.",
  "content_type_hint": "Content type: application/json — Events: Push events only",
  "confirm": "Confirm",
  "cancel": "Cancel",
  "close": "Close",
  "copied_toast": "Copied to clipboard",
  "enable_error": "Error enabling webhook",
  "disable_confirm_title": "Disable webhook?",
  "disable_confirm_body": "The source will switch back to polling (schedule). The old secret will be deleted.",
  "disable_btn": "Disable",
  "disable_error": "Error disabling webhook",
  "rotate_dialog_title": "Rotate secret",
  "rotate_new_secret_label": "New secret (copy it now)",
  "rotate_error": "Error rotating secret",
  "badge_webhook": "Webhook",
  "badge_schedule": "Schedule",
  "menu_enable": "Enable webhook",
  "menu_rotate": "Rotate secret",
  "menu_disable": "Disable webhook"
}
```

- [ ] **Step 6 : Enregistrer le namespace dans i18n config**

Dans `frontend/src/lib/i18n.ts` (ou fichier équivalent qui charge les namespaces), ajouter l'import :

```typescript
import gitWebhooksFr from "../i18n/fr/git_webhooks.json";
import gitWebhooksEn from "../i18n/en/git_webhooks.json";
```

Et dans la config des ressources :
```typescript
fr: { ..., git_webhooks: gitWebhooksFr },
en: { ..., git_webhooks: gitWebhooksEn },
```

- [ ] **Step 7 : Vérifier TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

Expected : 0 erreurs

- [ ] **Step 8 : Commit**

```bash
git add frontend/src/lib/source-webhooks.types.ts \
        frontend/src/lib/source-webhooks.ts \
        frontend/src/hooks/useSourceWebhooks.ts \
        frontend/src/i18n/fr/git_webhooks.json \
        frontend/src/i18n/en/git_webhooks.json \
        frontend/src/lib/workspaces.types.ts \
        frontend/src/lib/i18n.ts
git commit -m "feat(front): types + hooks + i18n git_webhooks"
```

---

## Task 9 — Frontend UI : dialogs + badge dans WorkspaceSourcesTab

**Files:**
- Create: `frontend/src/pages/workspace/EnableWebhookDialog.tsx`
- Create: `frontend/src/pages/workspace/RotateWebhookSecretDialog.tsx`
- Modify: `frontend/src/pages/workspace/WorkspaceSourcesTab.tsx`

- [ ] **Step 1 : Créer `EnableWebhookDialog.tsx`**

```tsx
// frontend/src/pages/workspace/EnableWebhookDialog.tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Check } from "lucide-react";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useEnableWebhook } from "@/hooks/useSourceWebhooks";
import { useToast } from "@/hooks/useToast";
import type { WebhookEnableResponse } from "@/lib/source-webhooks.types";

interface Props {
  workspaceName: string;
  sourceName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EnableWebhookDialog({ workspaceName, sourceName, open, onOpenChange }: Props) {
  const { t } = useTranslation("git_webhooks");
  const { toast } = useToast();
  const mutation = useEnableWebhook(workspaceName);
  const [result, setResult] = useState<WebhookEnableResponse | null>(null);
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [copiedSecret, setCopiedSecret] = useState(false);

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) { setResult(null); setCopiedUrl(false); setCopiedSecret(false); }
  }

  async function handleConfirm() {
    try {
      const res = await mutation.mutateAsync(sourceName);
      setResult(res);
    } catch {
      toast({ title: t("enable_error"), variant: "destructive" });
    }
  }

  async function copy(text: string, setCopied: (v: boolean) => void) {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    toast({ title: t("copied_toast") });
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{t("enable_dialog_title")}</DialogTitle>
        </DialogHeader>

        {!result ? (
          <>
            <p className="text-sm text-slate-600">
              {t("content_type_hint")}
            </p>
            <DialogFooter>
              <Button variant="outline" onClick={() => handleClose(false)}>{t("cancel")}</Button>
              <Button onClick={handleConfirm} disabled={mutation.isPending}>{t("confirm")}</Button>
            </DialogFooter>
          </>
        ) : (
          <div className="space-y-4">
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-500">
                {t("url_label")}
              </Label>
              <div className="flex items-center gap-2 mt-1">
                <Input value={result.webhook_url} readOnly className="font-mono text-xs bg-slate-50" />
                <Button size="sm" onClick={() => copy(result.webhook_url, setCopiedUrl)} className="shrink-0">
                  {copiedUrl ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>
              </div>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-500">
                {t("secret_label")}
              </Label>
              <p className="text-xs text-amber-600 mt-1">{t("secret_warning")}</p>
              <div className="flex items-center gap-2 mt-1">
                <Input value={result.secret} readOnly className="font-mono text-xs bg-slate-50" />
                <Button size="sm" onClick={() => copy(result.secret, setCopiedSecret)} className="shrink-0">
                  {copiedSecret ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>
              </div>
            </div>
            <p className="text-xs text-slate-500">{t("content_type_hint")}</p>
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

- [ ] **Step 2 : Créer `RotateWebhookSecretDialog.tsx`**

```tsx
// frontend/src/pages/workspace/RotateWebhookSecretDialog.tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Check } from "lucide-react";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useRotateWebhookSecret } from "@/hooks/useSourceWebhooks";
import { useToast } from "@/hooks/useToast";

interface Props {
  workspaceName: string;
  sourceName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RotateWebhookSecretDialog({ workspaceName, sourceName, open, onOpenChange }: Props) {
  const { t } = useTranslation("git_webhooks");
  const { toast } = useToast();
  const mutation = useRotateWebhookSecret(workspaceName);
  const [newSecret, setNewSecret] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) { setNewSecret(null); setCopied(false); }
  }

  async function handleRotate() {
    try {
      const res = await mutation.mutateAsync(sourceName);
      setNewSecret(res.secret);
    } catch {
      toast({ title: t("rotate_error"), variant: "destructive" });
    }
  }

  async function handleCopy() {
    if (!newSecret) return;
    await navigator.clipboard.writeText(newSecret);
    setCopied(true);
    toast({ title: t("copied_toast") });
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("rotate_dialog_title")}</DialogTitle>
        </DialogHeader>

        {!newSecret ? (
          <DialogFooter>
            <Button variant="outline" onClick={() => handleClose(false)}>{t("cancel")}</Button>
            <Button onClick={handleRotate} disabled={mutation.isPending}>{t("confirm")}</Button>
          </DialogFooter>
        ) : (
          <div className="space-y-4">
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-500">
                {t("rotate_new_secret_label")}
              </Label>
              <p className="text-xs text-amber-600 mt-1">{t("secret_warning")}</p>
              <div className="flex items-center gap-2 mt-1">
                <Input value={newSecret} readOnly className="font-mono text-xs bg-slate-50" />
                <Button size="sm" onClick={handleCopy} className="shrink-0">
                  {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>
              </div>
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

- [ ] **Step 3 : Modifier `WorkspaceSourcesTab.tsx`**

Lire le fichier existant, puis :

1. Ajouter les imports :
```tsx
import { useTranslation } from "react-i18next";  // si absent
import { EnableWebhookDialog } from "./EnableWebhookDialog";
import { RotateWebhookSecretDialog } from "./RotateWebhookSecretDialog";
import { useDisableWebhook } from "@/hooks/useSourceWebhooks";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
```

2. Ajouter les états dans le composant :
```tsx
const { t: tWh } = useTranslation("git_webhooks");
const disableMutation = useDisableWebhook(workspaceName);
const [webhookEnableTarget, setWebhookEnableTarget] = useState<string | null>(null);
const [webhookRotateTarget, setWebhookRotateTarget] = useState<string | null>(null);
const [webhookDisableTarget, setWebhookDisableTarget] = useState<string | null>(null);
```

3. Sur chaque ligne de source, ajouter le badge mode et les actions webhook dans le menu :

```tsx
{/* Badge mode */}
{source.webhook_enabled ? (
  <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-emerald-100 text-emerald-700">
    {tWh("badge_webhook")}
  </span>
) : (
  <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-slate-100 text-slate-500">
    {tWh("badge_schedule")}
  </span>
)}

{/* Dans le DropdownMenu de la source */}
{!source.webhook_enabled && (
  <DropdownMenuItem onSelect={() => setWebhookEnableTarget(source.name)}>
    {tWh("menu_enable")}
  </DropdownMenuItem>
)}
{source.webhook_enabled && (
  <>
    <DropdownMenuItem onSelect={() => setWebhookRotateTarget(source.name)}>
      {tWh("menu_rotate")}
    </DropdownMenuItem>
    <DropdownMenuItem
      onSelect={() => setWebhookDisableTarget(source.name)}
      className="text-rose-600"
    >
      {tWh("menu_disable")}
    </DropdownMenuItem>
  </>
)}
```

4. Ajouter les dialogs à la fin du JSX :
```tsx
{webhookEnableTarget && (
  <EnableWebhookDialog
    workspaceName={workspaceName}
    sourceName={webhookEnableTarget}
    open={!!webhookEnableTarget}
    onOpenChange={(o) => { if (!o) setWebhookEnableTarget(null); }}
  />
)}
{webhookRotateTarget && (
  <RotateWebhookSecretDialog
    workspaceName={workspaceName}
    sourceName={webhookRotateTarget}
    open={!!webhookRotateTarget}
    onOpenChange={(o) => { if (!o) setWebhookRotateTarget(null); }}
  />
)}
<AlertDialog
  open={!!webhookDisableTarget}
  onOpenChange={(o) => { if (!o) setWebhookDisableTarget(null); }}
>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>{tWh("disable_confirm_title")}</AlertDialogTitle>
      <AlertDialogDescription>{tWh("disable_confirm_body")}</AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel>{tWh("cancel")}</AlertDialogCancel>
      <AlertDialogAction
        onClick={() => {
          if (webhookDisableTarget) {
            disableMutation.mutate(webhookDisableTarget, {
              onSuccess: () => setWebhookDisableTarget(null),
            });
          }
        }}
        className="bg-rose-600 hover:bg-rose-700"
      >
        {tWh("disable_btn")}
      </AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

- [ ] **Step 4 : Vérifier TypeScript + lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Expected : 0 erreurs TypeScript

- [ ] **Step 5 : Commit**

```bash
git add frontend/src/pages/workspace/EnableWebhookDialog.tsx \
        frontend/src/pages/workspace/RotateWebhookSecretDialog.tsx \
        frontend/src/pages/workspace/WorkspaceSourcesTab.tsx
git commit -m "feat(front): UI webhooks git — badge Schedule/Webhook + dialogs enable/rotate/disable"
```

---

## Self-review

**Couverture spec :**
- ✅ Migration `webhook_enabled` (Task 1)
- ✅ Validateurs HMAC tous providers (Task 2)
- ✅ Parseurs de branche tous providers (Task 3)
- ✅ Service enable/disable/rotate + Harpocrate (Task 4)
- ✅ Endpoint `POST /api/webhooks/git/{ws}/{src}` (Task 5)
- ✅ API admin 3 endpoints (Task 6)
- ✅ Scheduler filtre webhook_enabled (Task 7)
- ✅ Types + hooks + i18n (Task 8)
- ✅ UI badge + dialogs (Task 9)
- ✅ Branche filtre silencieux (Task 5 flow step 4)
- ✅ Désactivation → next_sync_at = now() (Task 4)
- ✅ RAG_PUBLIC_URL pour construction de l'URL webhook (Task 6 via `settings.rag_public_url`)

**Consistance types :**
- `WebhookEnableResponse.secret` → utilisé dans `EnableWebhookDialog` ✅
- `WebhookRotateResponse.secret` → utilisé dans `RotateWebhookSecretDialog` ✅
- `Source.webhook_enabled: boolean` → utilisé dans `WorkspaceSourcesTab` ✅
- `enable_webhook()` retourne `str` → mappé dans endpoint admin ✅
