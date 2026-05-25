# M5c-backend — Coffres Harpocrate configurables côté DB Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrer la config Harpocrate du `.env` vers une table DB chiffrée `harpocrate_vaults` (pgcrypto) + API admin CRUD (9 endpoints) + refactor `SecretResolver` en provider DB-first avec fallback env + seed automatique au boot.

**Architecture:** Table `harpocrate_vaults` chiffrée pgcrypto (DEK = `HARPOCRATE_DEK` ≥32 chars). Service `HarpocrateVaultsService` (CRUD + cache default 60s). Router `/api/admin/harpocrate-vaults` (8 méthodes verbe-spécifiques + reveal-api-key). `HarpocrateClientProvider` charge dynamiquement clients DB-first ; fallback env si DB vide. `SecretResolver` devient async. 7 sites métier consomment `build_ref(default_vault_name, path)`. Bootstrap seed env→DB préserve les refs `${vault://rag:...}` existantes.

**Tech Stack:** Python 3.12 + asyncpg + pgcrypto + Pydantic v2 + FastAPI + structlog. Spec design : `docs/superpowers/specs/2026-05-16-M5c-backend-harpocrate-vaults-design.md`.

---

## File Structure

| Fichier | Statut | Responsabilité |
|---|---|---|
| `backend/src/rag/config.py` | **Modify** | Suppression validator harpocrate_api_keys + ajout `harpocrate_dek: SecretStr \| None` |
| `backend/migrations/009_harpocrate_vaults.sql` | **Create** | Table + index unique partiel + trigger updated_at |
| `backend/src/rag/secrets/refs.py` | **Create** | `parse_ref` / `build_ref` / `is_vault_ref` (pur, sans I/O) |
| `backend/src/rag/secrets/exceptions.py` | **Create** | `HarpocrateVaultsError`, `HarpocrateDekMissingError`, `VaultNameAlreadyExistsError`, `VaultNotFoundError` |
| `backend/src/rag/schemas/harpocrate_vaults.py` | **Create** | DTOs Pydantic v2 (Summary, Create, Update, Rotate, TestResult, Reveal) |
| `backend/src/rag/services/harpocrate_vaults.py` | **Create** | `HarpocrateVaultsService` (CRUD + chiffrement + cache default) |
| `backend/src/rag/secrets/client_provider.py` | **Create** | `HarpocrateClientProvider` (DB-first + fallback env, cache TTL 60s) |
| `backend/src/rag/secrets/resolver.py` | **Modify** | Constructeur → `client_provider` ; `resolve_ref` async |
| `backend/src/rag/secrets/bootstrap.py` | **Create** | `seed_vaults_from_env_if_empty` |
| `backend/src/rag/api/admin/harpocrate_vaults.py` | **Create** | Router 9 endpoints sous `require_master_key_or_oidc_role("rag-admin")` |
| `backend/src/rag/services/workspaces.py` | **Modify** | `_to_vault_ref(logical_key, vault_name)` ; param `default_vault_name` |
| `backend/src/rag/services/sources.py` | **Modify** | `build_ref(default_vault_name, path)` ; param |
| `backend/src/rag/services/jobs.py` | **Modify** | idem |
| `backend/src/rag/services/mcp.py` | **Modify** | idem |
| `backend/src/rag/services/oidc.py` | **Modify** | idem |
| `backend/src/rag/indexer/real.py` | **Modify** | param `default_vault_name` |
| `backend/src/rag/sync/executor.py` | **Modify** | Worker tient `client_provider`, résout default à chaque tick |
| `backend/src/rag/main.py` | **Modify** | Lifespan : `vaults_service` + `client_provider` + `seed` + `resolver` async |
| `.env.example` | **Modify** | Ajout `HARPOCRATE_DEK` + doc seed env |
| `backend/tests/unit/secrets/test_refs.py` | **Create** | parse_ref/build_ref/is_vault_ref |
| `backend/tests/unit/secrets/test_client_provider.py` | **Create** | Load DB / fallback env / invalidate / lock |
| `backend/tests/unit/secrets/test_resolver_async.py` | **Modify** | Adapter à signature async + provider |
| `backend/tests/unit/services/test_harpocrate_vaults_service.py` | **Create** | CRUD + cache + test_connection (SDK mocké) |
| `backend/tests/unit/schemas/test_harpocrate_vaults_dto.py` | **Create** | Validators Pydantic |
| `backend/tests/api/test_admin_harpocrate_vaults.py` | **Create** | 9 endpoints + codes erreurs + audit |
| `backend/tests/api/test_seed_bootstrap.py` | **Create** | 4 scénarios seed |
| `backend/tests/api/test_lifespan_empty_state.py` | **Create** | Boot avec DB vide + env vide → 503 sur write |

---

## Task 1: Ajouter `HARPOCRATE_DEK` à Settings + relaxer le validator

**Files:**
- Modify: `backend/src/rag/config.py`
- Create: `backend/tests/unit/test_settings_harpocrate_dek.py`

- [ ] **Step 1: Écrire les tests pour `harpocrate_dek`**

`backend/tests/unit/test_settings_harpocrate_dek.py` :

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.config import Settings


def _base_env(**overrides):
    base = {
        "RAG_MASTER_KEY": "x" * 64,
        "DATABASE_URL": "postgresql://u:p@localhost:5432/db",
        "REDIS_URL": "redis://localhost:6379/0",
    }
    base.update(overrides)
    return base


def test_dek_optional_when_absent(monkeypatch):
    for k, v in _base_env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("HARPOCRATE_DEK", raising=False)
    settings = Settings()
    assert settings.harpocrate_dek is None


def test_dek_accepts_32_chars(monkeypatch):
    for k, v in _base_env(HARPOCRATE_DEK="a" * 32).items():
        monkeypatch.setenv(k, v)
    settings = Settings()
    assert settings.harpocrate_dek is not None
    assert settings.harpocrate_dek.get_secret_value() == "a" * 32


def test_dek_under_32_chars_rejected(monkeypatch):
    for k, v in _base_env(HARPOCRATE_DEK="short").items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ValidationError, match="HARPOCRATE_DEK"):
        Settings()


def test_harpocrate_api_keys_now_optional(monkeypatch):
    """Le validator strict de M4 est supprimé : un boot sans env Harpocrate doit
    être autorisé (la résolution échouera en runtime si aucun coffre n'est en DB)."""
    for k, v in _base_env().items():
        monkeypatch.setenv(k, v)
    for k in list(monkeypatch._setitem):  # nettoyer toute paire Harpocrate
        pass
    monkeypatch.delenv("HARPOCRATE_API_TOKEN_RAG", raising=False)
    monkeypatch.delenv("HARPOCRATE_API_URL_RAG", raising=False)
    settings = Settings()
    assert settings.harpocrate_api_keys == {}
```

- [ ] **Step 2: Lancer les tests, ils doivent échouer**

```powershell
cd backend
uv run pytest tests/unit/test_settings_harpocrate_dek.py -v
```

Expected : 4 FAIL (champ `harpocrate_dek` absent, validator existant rejette env vide).

- [ ] **Step 3: Modifier `backend/src/rag/config.py`**

Localiser la classe `Settings` et :

1. Supprimer le `model_validator` qui exige au moins une paire `harpocrate_api_keys` (laisser `harpocrate_api_keys: dict[...] = {}` par défaut).
2. Ajouter le champ `harpocrate_dek` :

```python
from pydantic import Field, SecretStr, field_validator


class Settings(BaseSettings):
    # ... champs existants ...

    harpocrate_dek: SecretStr | None = Field(
        default=None,
        description="Passphrase pgcrypto pour chiffrer les api_keys en DB. "
                    "Min 32 chars. Requis dès qu'un coffre est créé.",
    )

    @field_validator("harpocrate_dek")
    @classmethod
    def _validate_harpocrate_dek_length(cls, v: SecretStr | None) -> SecretStr | None:
        if v is None:
            return None
        raw = v.get_secret_value()
        if len(raw) < 32:
            raise ValueError("HARPOCRATE_DEK doit faire au moins 32 caractères")
        return v
```

- [ ] **Step 4: Lancer les tests, ils doivent passer**

```powershell
uv run pytest tests/unit/test_settings_harpocrate_dek.py -v
```

Expected : 4 PASS.

- [ ] **Step 5: Vérifier non-régression**

```powershell
uv run pytest tests/unit/ -v -x
```

Expected : tous les tests existants passent (la suppression du validator strict ne casse rien si les tests existants set déjà `HARPOCRATE_API_TOKEN_RAG`).

- [ ] **Step 6: Commit**

```powershell
git add backend/src/rag/config.py backend/tests/unit/test_settings_harpocrate_dek.py
git commit -m "feat(M5c): Settings.harpocrate_dek + relaxation harpocrate_api_keys"
```

---

## Task 2: Migration SQL `009_harpocrate_vaults.sql`

**Files:**
- Create: `backend/migrations/009_harpocrate_vaults.sql`
- Create: `backend/tests/integration/test_migration_009_harpocrate_vaults.py`

**Conventions projet à respecter (vérifiées par lecture du repo)** :
- La fixture `db_conn` n'existe pas. Le pattern projet utilise `session_pool: asyncpg.Pool` + `await run_migrations(session_pool, MIGRATIONS_DIR)` au début du test (cf. `tests/integration/test_services_sources.py:21,74`).
- `updated_at` n'est PAS maintenu par trigger. Les services Python font explicitement `SET ..., updated_at = now()` dans leurs UPDATE (cf. `services/workspaces.py:214,260`). La migration M5c NE crée PAS de trigger.

- [ ] **Step 1: Écrire le test de migration**

`backend/tests/integration/test_migration_009_harpocrate_vaults.py` :

```python
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_harpocrate_vaults_table_exists(session_pool: asyncpg.Pool):
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT to_regclass('public.harpocrate_vaults') AS table_oid"
        )
    assert row["table_oid"] is not None


@pytest.mark.asyncio
async def test_unique_default_index(session_pool: asyncpg.Pool):
    """L'index unique partiel empêche deux coffres is_default=true simultanés."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    passphrase = "passphrase-of-at-least-32-characters-long"
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        await conn.execute(
            """
            INSERT INTO harpocrate_vaults (id, name, label, base_url, api_key_id,
                api_key_encrypted, is_default)
            VALUES (gen_random_uuid(), 'a', 'A', 'https://a', 'k1',
                pgp_sym_encrypt('secret', $1), true)
            """,
            passphrase,
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                """
                INSERT INTO harpocrate_vaults (id, name, label, base_url, api_key_id,
                    api_key_encrypted, is_default)
                VALUES (gen_random_uuid(), 'b', 'B', 'https://b', 'k2',
                    pgp_sym_encrypt('secret', $1), true)
                """,
                passphrase,
            )
        await conn.execute("DELETE FROM harpocrate_vaults")


@pytest.mark.asyncio
async def test_pgp_roundtrip(session_pool: asyncpg.Pool):
    """pgp_sym_encrypt + pgp_sym_decrypt avec la passphrase doit redonner la valeur claire."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    passphrase = "passphrase-of-at-least-32-characters-long"
    async with session_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pgp_sym_decrypt(
                pgp_sym_encrypt('the-secret-value', $1),
                $1
            )::text AS plain
            """,
            passphrase,
        )
    assert row["plain"] == "the-secret-value"
```

- [ ] **Step 2: Lancer les tests, ils doivent échouer**

```powershell
cd backend
uv run pytest tests/integration/test_migration_009_harpocrate_vaults.py -v
```

Expected : FAIL (table inexistante).

- [ ] **Step 3: Créer `backend/migrations/009_harpocrate_vaults.sql`**

```sql
-- Migration 009 : coffres Harpocrate configurables côté DB (M5c)
-- Pré-requis : pgcrypto (activé en 001_init.sql)
-- Note : updated_at est maintenu côté service Python (pas de trigger), conformément
-- à la convention projet (cf. services/workspaces.py).

CREATE TABLE harpocrate_vaults (
    id                uuid PRIMARY KEY,
    name              text NOT NULL UNIQUE,
    label             text NOT NULL,
    base_url          text NOT NULL,
    api_key_id        text NOT NULL,
    api_key_encrypted bytea NOT NULL,
    probe_path        text NULL,
    is_default        boolean NOT NULL DEFAULT false,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX harpocrate_vaults_one_default
    ON harpocrate_vaults (is_default)
    WHERE is_default;

CREATE INDEX harpocrate_vaults_name ON harpocrate_vaults (name);
```

- [ ] **Step 4: Relancer les tests d'intégration**

```powershell
uv run pytest tests/integration/test_migration_009_harpocrate_vaults.py -v
```

Expected : 3 PASS. La fixture `session_pool` crée une base test jetable et le test applique `run_migrations` lui-même.

- [ ] **Step 5: Commit**

```powershell
git add backend/migrations/009_harpocrate_vaults.sql backend/tests/integration/test_migration_009_harpocrate_vaults.py
git commit -m "feat(M5c): migration 009 harpocrate_vaults (pgcrypto + index unique partiel)"
```

---

## Task 3: Helpers `secrets/refs.py`

**Files:**
- Create: `backend/src/rag/secrets/refs.py`
- Create: `backend/tests/unit/secrets/test_refs.py`

- [ ] **Step 1: Écrire les tests**

`backend/tests/unit/secrets/test_refs.py` :

```python
from __future__ import annotations

import pytest

from rag.secrets.refs import build_ref, is_vault_ref, parse_ref


@pytest.mark.parametrize("ref, expected", [
    ("${vault://rag:openai_key}", ("rag", "openai_key")),
    ("${vault://prod-v2:secrets/keycloak/client}", ("prod-v2", "secrets/keycloak/client")),
    ("${vault://a:b}", ("a", "b")),
])
def test_parse_ref_valid(ref, expected):
    assert parse_ref(ref) == expected


@pytest.mark.parametrize("ref", [
    "",
    "openai_key",
    "${vault://rag}",
    "${vault://rag:}",
    "${vault://:path}",
    "vault://rag:path",
    "${vault://rag:path}extra",
    "prefix${vault://rag:path}",
])
def test_parse_ref_invalid_raises(ref):
    with pytest.raises(ValueError, match="ref Harpocrate invalide"):
        parse_ref(ref)


def test_build_ref_roundtrip():
    assert build_ref("rag", "openai_key") == "${vault://rag:openai_key}"
    assert parse_ref(build_ref("prod", "secrets/x/y")) == ("prod", "secrets/x/y")


def test_is_vault_ref():
    assert is_vault_ref("${vault://rag:openai_key}") is True
    assert is_vault_ref("plain string") is False
    assert is_vault_ref("") is False
```

- [ ] **Step 2: Lancer, ils doivent échouer (module inexistant)**

```powershell
uv run pytest tests/unit/secrets/test_refs.py -v
```

Expected : FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implémenter `backend/src/rag/secrets/refs.py`**

```python
from __future__ import annotations

import re

_VAULT_RE = re.compile(r"^\$\{vault://([^:}]+):([^}]+)\}$")


def parse_ref(ref: str) -> tuple[str, str]:
    """Extrait (vault_name, path) depuis `${vault://<name>:<path>}`.

    Raise ValueError si le format ne matche pas. Pas d'I/O.
    """
    match = _VAULT_RE.match(ref)
    if not match:
        raise ValueError(f"ref Harpocrate invalide: {ref!r}")
    return match.group(1), match.group(2)


def build_ref(vault_name: str, path: str) -> str:
    return f"${{vault://{vault_name}:{path}}}"


def is_vault_ref(value: str) -> bool:
    return bool(_VAULT_RE.match(value))
```

- [ ] **Step 4: Lancer, tous doivent passer**

```powershell
uv run pytest tests/unit/secrets/test_refs.py -v
```

Expected : 12 PASS (3 + 8 + 1 + 1 = 13 cas paramétrés et tests).

- [ ] **Step 5: Commit**

```powershell
git add backend/src/rag/secrets/refs.py backend/tests/unit/secrets/test_refs.py
git commit -m "feat(M5c): helpers refs parse_ref/build_ref/is_vault_ref"
```

---

## Task 4: Exceptions + Schemas Pydantic

**Files:**
- Create: `backend/src/rag/secrets/exceptions.py`
- Create: `backend/src/rag/schemas/harpocrate_vaults.py`
- Create: `backend/tests/unit/schemas/test_harpocrate_vaults_dto.py`

- [ ] **Step 1: Écrire les tests des schemas**

`backend/tests/unit/schemas/test_harpocrate_vaults_dto.py` :

```python
from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from rag.schemas.harpocrate_vaults import (
    VaultCreateRequest,
    VaultUpdateRequest,
    VaultRotateApiKeyRequest,
)


def _valid_create_payload(**overrides):
    payload = {
        "name": "rag",
        "label": "Coffre RAG",
        "base_url": "https://harpocrate.yoops.org",
        "api_key_id": "k-001",
        "api_key": "secretvalueX" * 4,
        "is_default": True,
    }
    payload.update(overrides)
    return payload


def test_create_valid():
    req = VaultCreateRequest(**_valid_create_payload())
    assert req.name == "rag"
    assert req.base_url == "https://harpocrate.yoops.org"


@pytest.mark.parametrize("bad_name", [
    "A", "ra", "1rag", "rag!", "rag space", "_rag", "x" * 65,
])
def test_create_name_validation(bad_name):
    with pytest.raises(ValidationError):
        VaultCreateRequest(**_valid_create_payload(name=bad_name))


def test_create_base_url_strips_trailing_slash():
    req = VaultCreateRequest(**_valid_create_payload(base_url="https://h.org/"))
    assert req.base_url == "https://h.org"


def test_create_base_url_requires_http_scheme():
    with pytest.raises(ValidationError, match="http"):
        VaultCreateRequest(**_valid_create_payload(base_url="ftp://h.org"))


def test_create_probe_path_validation():
    req = VaultCreateRequest(**_valid_create_payload(probe_path="path/to/secret"))
    assert req.probe_path == "path/to/secret"
    with pytest.raises(ValidationError):
        VaultCreateRequest(**_valid_create_payload(probe_path="bad path with spaces"))
    req2 = VaultCreateRequest(**_valid_create_payload(probe_path=""))
    assert req2.probe_path is None


def test_update_forbids_name_field():
    with pytest.raises(ValidationError, match="extra"):
        VaultUpdateRequest(name="newname")


def test_update_forbids_is_default_field():
    with pytest.raises(ValidationError, match="extra"):
        VaultUpdateRequest(is_default=True)


def test_update_partial_label_only():
    req = VaultUpdateRequest(label="new label")
    assert req.label == "new label"
    assert req.base_url is None


def test_rotate_requires_both_fields():
    req = VaultRotateApiKeyRequest(api_key_id="k-002", api_key="newvalue1234")
    assert req.api_key_id == "k-002"
    with pytest.raises(ValidationError):
        VaultRotateApiKeyRequest(api_key="x" * 12)  # api_key_id manquant
```

- [ ] **Step 2: Lancer, doivent échouer (module schemas inexistant)**

```powershell
uv run pytest tests/unit/schemas/test_harpocrate_vaults_dto.py -v
```

Expected : FAIL.

- [ ] **Step 3: Créer `backend/src/rag/secrets/exceptions.py`**

```python
from __future__ import annotations


class HarpocrateVaultsError(Exception):
    """Base pour toutes les erreurs liées aux coffres Harpocrate."""


class HarpocrateDekMissingError(HarpocrateVaultsError):
    """HARPOCRATE_DEK requis mais absent alors qu'au moins un coffre existe en DB."""


class VaultNameAlreadyExistsError(HarpocrateVaultsError):
    """Le nom de coffre est déjà utilisé."""


class VaultNotFoundError(HarpocrateVaultsError):
    """Le coffre demandé n'existe pas."""
```

- [ ] **Step 4: Créer `backend/src/rag/schemas/harpocrate_vaults.py`**

```python
from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
_PROBE_RE = re.compile(r"^[a-zA-Z0-9_/-]+$")


class VaultSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    label: str
    base_url: str
    api_key_id: str
    probe_path: str | None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class VaultCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=8, max_length=512)
    api_key_id: str = Field(min_length=1, max_length=128)
    api_key: str = Field(min_length=8, max_length=2048)
    probe_path: str | None = None
    is_default: bool = False

    @field_validator("name")
    @classmethod
    def _v_name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError("name doit matcher ^[a-z][a-z0-9_-]{2,63}$")
        return v

    @field_validator("base_url")
    @classmethod
    def _v_base_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url doit commencer par http:// ou https://")
        return v.rstrip("/")

    @field_validator("probe_path")
    @classmethod
    def _v_probe_path(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _PROBE_RE.match(v):
            raise ValueError("probe_path : caractères autorisés [a-zA-Z0-9_/-]")
        return v


class VaultUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = Field(default=None, min_length=8, max_length=512)
    probe_path: str | None = Field(default=None, max_length=512)

    @field_validator("base_url")
    @classmethod
    def _v_base_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url doit commencer par http:// ou https://")
        return v.rstrip("/")

    @field_validator("probe_path")
    @classmethod
    def _v_probe_path(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _PROBE_RE.match(v):
            raise ValueError("probe_path : caractères autorisés [a-zA-Z0-9_/-]")
        return v


class VaultRotateApiKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key_id: str = Field(min_length=1, max_length=128)
    api_key: str = Field(min_length=8, max_length=2048)


class VaultTestConnectionResult(BaseModel):
    ok: bool
    detail: str
    probe_path_used: str


class VaultRevealApiKeyResponse(BaseModel):
    id: UUID
    api_key_id: str
    api_key: str
```

- [ ] **Step 5: Lancer, tous doivent passer**

```powershell
uv run pytest tests/unit/schemas/test_harpocrate_vaults_dto.py -v
```

Expected : tous PASS (~12 cas).

- [ ] **Step 6: Commit**

```powershell
git add backend/src/rag/secrets/exceptions.py backend/src/rag/schemas/harpocrate_vaults.py backend/tests/unit/schemas/test_harpocrate_vaults_dto.py
git commit -m "feat(M5c): exceptions + schemas Pydantic harpocrate_vaults"
```

---

## Task 5: Service `HarpocrateVaultsService` — reads + create

**Files:**
- Create: `backend/src/rag/services/harpocrate_vaults.py`
- Create: `backend/tests/unit/services/test_harpocrate_vaults_service_reads.py`
- Create: `backend/tests/unit/services/test_harpocrate_vaults_service_create.py`

- [ ] **Step 1: Écrire les tests reads + create**

`backend/tests/unit/services/test_harpocrate_vaults_service_reads.py` :

```python
from __future__ import annotations

from uuid import uuid4

import pytest

from rag.services.harpocrate_vaults import HarpocrateVaultsService
from rag.schemas.harpocrate_vaults import VaultCreateRequest


@pytest.fixture
def dek():
    return "x" * 64


@pytest.fixture
def service(settings_with_dek):
    return HarpocrateVaultsService(settings_with_dek)


@pytest.mark.asyncio
async def test_list_all_empty(db_conn, service):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    assert await service.list_all(db_conn) == []


@pytest.mark.asyncio
async def test_get_by_id_returns_none_when_absent(db_conn, service):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    assert await service.get_by_id(db_conn, uuid4()) is None


@pytest.mark.asyncio
async def test_get_by_name_returns_none_when_absent(db_conn, service):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    assert await service.get_by_name(db_conn, "absent") is None


@pytest.mark.asyncio
async def test_get_default_returns_none_when_empty(db_conn, service):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    assert await service.get_default(db_conn) is None


@pytest.mark.asyncio
async def test_reveal_api_key_returns_none_when_absent(db_conn, service):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    assert await service.reveal_api_key(db_conn, uuid4()) is None
```

`backend/tests/unit/services/test_harpocrate_vaults_service_create.py` :

```python
from __future__ import annotations

import pytest

from rag.services.harpocrate_vaults import HarpocrateVaultsService
from rag.secrets.exceptions import VaultNameAlreadyExistsError
from rag.schemas.harpocrate_vaults import VaultCreateRequest


def _req(**overrides):
    payload = {
        "name": "rag",
        "label": "Coffre RAG",
        "base_url": "https://harpocrate.yoops.org",
        "api_key_id": "k-001",
        "api_key": "supersecretvalue123",
        "is_default": True,
    }
    payload.update(overrides)
    return VaultCreateRequest(**payload)


@pytest.mark.asyncio
async def test_create_persists_and_returns_summary(db_conn, service):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    async with db_conn.transaction():
        summary = await service.create(db_conn, _req())
    assert summary.name == "rag"
    assert summary.is_default is True
    assert summary.id is not None

    revealed = await service.reveal_api_key(db_conn, summary.id)
    assert revealed == "supersecretvalue123"


@pytest.mark.asyncio
async def test_create_duplicate_name_raises(db_conn, service):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    async with db_conn.transaction():
        await service.create(db_conn, _req(name="dup"))
    with pytest.raises(VaultNameAlreadyExistsError):
        async with db_conn.transaction():
            await service.create(db_conn, _req(name="dup", api_key_id="k-002"))


@pytest.mark.asyncio
async def test_create_second_default_demotes_previous(db_conn, service):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    async with db_conn.transaction():
        first = await service.create(db_conn, _req(name="first", is_default=True))
    async with db_conn.transaction():
        second = await service.create(
            db_conn,
            _req(name="second", api_key_id="k-002", is_default=True),
        )
    refreshed_first = await service.get_by_id(db_conn, first.id)
    assert refreshed_first.is_default is False
    assert second.is_default is True
```

La fixture `settings_with_dek` est à ajouter dans `conftest.py` :

```python
@pytest.fixture
def settings_with_dek(monkeypatch):
    monkeypatch.setenv("HARPOCRATE_DEK", "passphrase-of-at-least-32-characters-long")
    from rag.config import Settings
    return Settings()
```

- [ ] **Step 2: Lancer, doivent échouer**

```powershell
uv run pytest tests/unit/services/test_harpocrate_vaults_service_reads.py tests/unit/services/test_harpocrate_vaults_service_create.py -v
```

Expected : FAIL.

- [ ] **Step 3: Implémenter `backend/src/rag/services/harpocrate_vaults.py` (reads + create)**

```python
from __future__ import annotations

import time
from uuid import UUID, uuid4

import structlog
from asyncpg import Connection, UniqueViolationError

from rag.config import Settings
from rag.schemas.harpocrate_vaults import (
    VaultCreateRequest,
    VaultRotateApiKeyRequest,
    VaultSummary,
    VaultUpdateRequest,
    VaultTestConnectionResult,
)
from rag.secrets.exceptions import (
    HarpocrateDekMissingError,
    VaultNameAlreadyExistsError,
    VaultNotFoundError,
)

log = structlog.get_logger(__name__)

_DEFAULT_CACHE_TTL_SECONDS = 60
_PROBE_PATH_FALLBACK = "__probe__"

_COLUMNS = (
    "id, name, label, base_url, api_key_id, probe_path, "
    "is_default, created_at, updated_at"
)


class HarpocrateVaultsService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._default_cache: tuple[float, VaultSummary | None] | None = None
        self._client_provider = None  # bind ultérieur

    def bind_client_provider(self, provider) -> None:
        self._client_provider = provider

    def _require_dek(self) -> str:
        dek = self._settings.harpocrate_dek
        if dek is None:
            raise HarpocrateDekMissingError(
                "HARPOCRATE_DEK manquant alors qu'au moins un coffre est requis"
            )
        return dek.get_secret_value()

    # --- Reads --------------------------------------------------------

    async def list_all(self, conn: Connection) -> list[VaultSummary]:
        rows = await conn.fetch(
            f"SELECT {_COLUMNS} FROM harpocrate_vaults ORDER BY created_at"
        )
        return [VaultSummary.model_validate(dict(r)) for r in rows]

    async def get_by_id(self, conn: Connection, vault_id: UUID) -> VaultSummary | None:
        row = await conn.fetchrow(
            f"SELECT {_COLUMNS} FROM harpocrate_vaults WHERE id = $1", vault_id
        )
        return VaultSummary.model_validate(dict(row)) if row else None

    async def get_by_name(self, conn: Connection, name: str) -> VaultSummary | None:
        row = await conn.fetchrow(
            f"SELECT {_COLUMNS} FROM harpocrate_vaults WHERE name = $1", name
        )
        return VaultSummary.model_validate(dict(row)) if row else None

    async def get_default(self, conn: Connection) -> VaultSummary | None:
        if self._default_cache is not None:
            ts, value = self._default_cache
            if time.monotonic() - ts < _DEFAULT_CACHE_TTL_SECONDS:
                return value
        row = await conn.fetchrow(
            f"SELECT {_COLUMNS} FROM harpocrate_vaults WHERE is_default = true"
        )
        value = VaultSummary.model_validate(dict(row)) if row else None
        self._default_cache = (time.monotonic(), value)
        return value

    async def reveal_api_key(self, conn: Connection, vault_id: UUID) -> str | None:
        dek = self._require_dek()
        row = await conn.fetchrow(
            "SELECT pgp_sym_decrypt(api_key_encrypted, $2::text)::text AS api_key "
            "FROM harpocrate_vaults WHERE id = $1",
            vault_id,
            dek,
        )
        return row["api_key"] if row else None

    # --- Writes -------------------------------------------------------

    async def create(self, conn: Connection, req: VaultCreateRequest) -> VaultSummary:
        dek = self._require_dek()
        vault_id = uuid4()

        if req.is_default:
            await conn.execute(
                "UPDATE harpocrate_vaults SET is_default = false WHERE is_default = true"
            )

        try:
            row = await conn.fetchrow(
                f"""
                INSERT INTO harpocrate_vaults
                    (id, name, label, base_url, api_key_id, api_key_encrypted,
                     probe_path, is_default)
                VALUES
                    ($1, $2, $3, $4, $5, pgp_sym_encrypt($6::text, $7::text),
                     $8, $9)
                RETURNING {_COLUMNS}
                """,
                vault_id, req.name, req.label, req.base_url, req.api_key_id,
                req.api_key, dek, req.probe_path, req.is_default,
            )
        except UniqueViolationError as exc:
            raise VaultNameAlreadyExistsError(req.name) from exc

        self._invalidate_caches()
        log.info("vault.created", vault_id=str(vault_id), name=req.name,
                 is_default=req.is_default)
        return VaultSummary.model_validate(dict(row))

    def _invalidate_caches(self) -> None:
        self._default_cache = None
        if self._client_provider is not None:
            self._client_provider.invalidate()
```

- [ ] **Step 4: Lancer, doivent passer**

```powershell
uv run pytest tests/unit/services/test_harpocrate_vaults_service_reads.py tests/unit/services/test_harpocrate_vaults_service_create.py -v
```

Expected : 8 PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/rag/services/harpocrate_vaults.py backend/tests/conftest.py backend/tests/unit/services/test_harpocrate_vaults_service_reads.py backend/tests/unit/services/test_harpocrate_vaults_service_create.py
git commit -m "feat(M5c): HarpocrateVaultsService reads + create (pgcrypto)"
```

---

## Task 6: Service `update`, `rotate_api_key`, `set_default`, `delete`

**Files:**
- Modify: `backend/src/rag/services/harpocrate_vaults.py`
- Create: `backend/tests/unit/services/test_harpocrate_vaults_service_writes.py`

- [ ] **Step 1: Écrire les tests writes**

`backend/tests/unit/services/test_harpocrate_vaults_service_writes.py` :

```python
from __future__ import annotations

import pytest

from rag.schemas.harpocrate_vaults import (
    VaultCreateRequest,
    VaultRotateApiKeyRequest,
    VaultUpdateRequest,
)


def _req(**overrides):
    payload = {
        "name": "rag",
        "label": "Coffre RAG",
        "base_url": "https://harpocrate.yoops.org",
        "api_key_id": "k-001",
        "api_key": "supersecretvalue123",
        "is_default": True,
    }
    payload.update(overrides)
    return VaultCreateRequest(**payload)


@pytest.fixture
async def seeded(db_conn, service):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    async with db_conn.transaction():
        v = await service.create(db_conn, _req())
    return v


@pytest.mark.asyncio
async def test_update_label_only(db_conn, service, seeded):
    updated = await service.update(
        db_conn, seeded.id, VaultUpdateRequest(label="Nouveau libellé")
    )
    assert updated.label == "Nouveau libellé"
    assert updated.base_url == seeded.base_url


@pytest.mark.asyncio
async def test_update_returns_none_when_absent(db_conn, service):
    from uuid import uuid4
    result = await service.update(db_conn, uuid4(), VaultUpdateRequest(label="x"))
    assert result is None


@pytest.mark.asyncio
async def test_rotate_api_key_changes_encrypted_value(db_conn, service, seeded):
    old_key = await service.reveal_api_key(db_conn, seeded.id)
    updated = await service.rotate_api_key(
        db_conn, seeded.id,
        VaultRotateApiKeyRequest(api_key_id="k-002", api_key="newsecretXYZ987"),
    )
    assert updated.api_key_id == "k-002"
    new_key = await service.reveal_api_key(db_conn, seeded.id)
    assert new_key == "newsecretXYZ987"
    assert new_key != old_key


@pytest.mark.asyncio
async def test_set_default_swaps_atomically(db_conn, service, seeded):
    async with db_conn.transaction():
        second = await service.create(
            db_conn, _req(name="second", api_key_id="k-002", is_default=False),
        )
    updated = await service.set_default(db_conn, second.id)
    assert updated.is_default is True
    first = await service.get_by_id(db_conn, seeded.id)
    assert first.is_default is False


@pytest.mark.asyncio
async def test_delete_returns_true(db_conn, service, seeded):
    # supprimer le seul coffre default → autorisé au niveau service
    assert await service.delete(db_conn, seeded.id) is True
    assert await service.get_by_id(db_conn, seeded.id) is None


@pytest.mark.asyncio
async def test_delete_returns_false_when_absent(db_conn, service):
    from uuid import uuid4
    assert await service.delete(db_conn, uuid4()) is False
```

- [ ] **Step 2: Lancer, doivent échouer**

```powershell
uv run pytest tests/unit/services/test_harpocrate_vaults_service_writes.py -v
```

- [ ] **Step 3: Étendre `services/harpocrate_vaults.py` avec les méthodes write**

Ajouter dans la classe `HarpocrateVaultsService` :

```python
    async def update(
        self,
        conn: Connection,
        vault_id: UUID,
        req: VaultUpdateRequest,
    ) -> VaultSummary | None:
        fields = req.model_dump(exclude_unset=True)
        if not fields:
            return await self.get_by_id(conn, vault_id)

        set_parts = []
        params: list = [vault_id]
        for i, (col, value) in enumerate(fields.items(), start=2):
            set_parts.append(f"{col} = ${i}")
            params.append(value)
        sql = (
            f"UPDATE harpocrate_vaults SET {', '.join(set_parts)} "
            f"WHERE id = $1 RETURNING {_COLUMNS}"
        )
        row = await conn.fetchrow(sql, *params)
        if row is None:
            return None
        self._invalidate_caches()
        log.info("vault.updated", vault_id=str(vault_id),
                 fields_changed=list(fields.keys()))
        return VaultSummary.model_validate(dict(row))

    async def rotate_api_key(
        self,
        conn: Connection,
        vault_id: UUID,
        req: VaultRotateApiKeyRequest,
    ) -> VaultSummary | None:
        dek = self._require_dek()
        previous = await self.get_by_id(conn, vault_id)
        if previous is None:
            return None
        row = await conn.fetchrow(
            f"""
            UPDATE harpocrate_vaults
            SET api_key_id = $2,
                api_key_encrypted = pgp_sym_encrypt($3::text, $4::text)
            WHERE id = $1
            RETURNING {_COLUMNS}
            """,
            vault_id, req.api_key_id, req.api_key, dek,
        )
        self._invalidate_caches()
        log.info(
            "vault.api_key_rotated",
            vault_id=str(vault_id),
            api_key_id_old=previous.api_key_id,
            api_key_id_new=req.api_key_id,
        )
        return VaultSummary.model_validate(dict(row))

    async def set_default(
        self,
        conn: Connection,
        vault_id: UUID,
    ) -> VaultSummary | None:
        target = await self.get_by_id(conn, vault_id)
        if target is None:
            return None
        async with conn.transaction():
            previous = await conn.fetchval(
                "SELECT id FROM harpocrate_vaults WHERE is_default = true"
            )
            await conn.execute(
                "UPDATE harpocrate_vaults SET is_default = false "
                "WHERE is_default = true"
            )
            row = await conn.fetchrow(
                f"UPDATE harpocrate_vaults SET is_default = true "
                f"WHERE id = $1 RETURNING {_COLUMNS}",
                vault_id,
            )
        self._invalidate_caches()
        log.info(
            "vault.default_changed",
            vault_id_old=str(previous) if previous else None,
            vault_id_new=str(vault_id),
        )
        return VaultSummary.model_validate(dict(row))

    async def delete(self, conn: Connection, vault_id: UUID) -> bool:
        result = await conn.execute(
            "DELETE FROM harpocrate_vaults WHERE id = $1", vault_id
        )
        deleted = result.endswith(" 1")
        if deleted:
            self._invalidate_caches()
            log.info("vault.deleted", vault_id=str(vault_id))
        return deleted
```

Note : `set_default` ouvre sa propre transaction interne pour atomicité même si l'appelant n'en ouvre pas une (acceptable car opération multi-statement).

- [ ] **Step 4: Lancer, tous doivent passer**

```powershell
uv run pytest tests/unit/services/test_harpocrate_vaults_service_writes.py -v
```

Expected : 6 PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/rag/services/harpocrate_vaults.py backend/tests/unit/services/test_harpocrate_vaults_service_writes.py
git commit -m "feat(M5c): HarpocrateVaultsService update/rotate/set_default/delete"
```

---

## Task 7: Service `test_connection`

**Files:**
- Modify: `backend/src/rag/services/harpocrate_vaults.py`
- Create: `backend/tests/unit/services/test_harpocrate_vaults_service_test_connection.py`

- [ ] **Step 1: Écrire les tests**

`backend/tests/unit/services/test_harpocrate_vaults_service_test_connection.py` :

```python
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from rag.schemas.harpocrate_vaults import VaultCreateRequest


def _req(**overrides):
    payload = {
        "name": "rag", "label": "Coffre RAG",
        "base_url": "https://harpocrate.yoops.org",
        "api_key_id": "k-001", "api_key": "supersecretvalue123",
        "is_default": True,
    }
    payload.update(overrides)
    return VaultCreateRequest(**payload)


@pytest.fixture
async def seeded_with_probe(db_conn, service):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    async with db_conn.transaction():
        v = await service.create(db_conn, _req(probe_path="known/secret"))
    return v


@pytest.fixture
async def seeded_no_probe(db_conn, service):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    async with db_conn.transaction():
        v = await service.create(db_conn, _req())
    return v


@pytest.mark.asyncio
async def test_test_connection_returns_ok_when_secret_resolved(
    db_conn, service, seeded_with_probe,
):
    with patch("rag.services.harpocrate_vaults.HarpocrateVaultClient") as MockClient:
        instance = MagicMock()
        instance.get_secret.return_value = "ok"
        MockClient.return_value = instance
        result = await service.test_connection(db_conn, seeded_with_probe.id)
    assert result.ok is True
    assert "résolu" in result.detail
    assert result.probe_path_used == "known/secret"


@pytest.mark.asyncio
async def test_test_connection_401_returns_ko(db_conn, service, seeded_with_probe):
    class FakeResponse:
        status_code = 401
    class FakeError(Exception):
        def __init__(self):
            self.response = FakeResponse()

    with patch("rag.services.harpocrate_vaults.HarpocrateVaultClient") as MockClient:
        instance = MagicMock()
        instance.get_secret.side_effect = FakeError()
        MockClient.return_value = instance
        result = await service.test_connection(db_conn, seeded_with_probe.id)
    assert result.ok is False
    assert "auth refusée" in result.detail


@pytest.mark.asyncio
async def test_test_connection_404_with_probe_path_configured_is_ko(
    db_conn, service, seeded_with_probe,
):
    class FakeResponse:
        status_code = 404
    class FakeError(Exception):
        def __init__(self):
            self.response = FakeResponse()

    with patch("rag.services.harpocrate_vaults.HarpocrateVaultClient") as MockClient:
        instance = MagicMock()
        instance.get_secret.side_effect = FakeError()
        MockClient.return_value = instance
        result = await service.test_connection(db_conn, seeded_with_probe.id)
    assert result.ok is False
    assert "introuvable" in result.detail


@pytest.mark.asyncio
async def test_test_connection_404_without_probe_path_is_ok(
    db_conn, service, seeded_no_probe,
):
    class FakeResponse:
        status_code = 404
    class FakeError(Exception):
        def __init__(self):
            self.response = FakeResponse()

    with patch("rag.services.harpocrate_vaults.HarpocrateVaultClient") as MockClient:
        instance = MagicMock()
        instance.get_secret.side_effect = FakeError()
        MockClient.return_value = instance
        result = await service.test_connection(db_conn, seeded_no_probe.id)
    assert result.ok is True
    assert "auth ok" in result.detail
    assert result.probe_path_used == "__probe__"
```

- [ ] **Step 2: Lancer, doivent échouer**

```powershell
uv run pytest tests/unit/services/test_harpocrate_vaults_service_test_connection.py -v
```

- [ ] **Step 3: Étendre le service**

Ajouter en haut du fichier :

```python
from rag.secrets.vault import HarpocrateVaultClient
```

Puis ajouter la méthode :

```python
    async def test_connection(
        self,
        conn: Connection,
        vault_id: UUID,
    ) -> VaultTestConnectionResult:
        vault = await self.get_by_id(conn, vault_id)
        if vault is None:
            raise VaultNotFoundError(str(vault_id))

        api_key = await self.reveal_api_key(conn, vault_id)
        if api_key is None:
            raise VaultNotFoundError(str(vault_id))

        path = vault.probe_path or _PROBE_PATH_FALLBACK
        try:
            client = HarpocrateVaultClient(url=vault.base_url, token=api_key)
            client.get_secret(path)
            return VaultTestConnectionResult(
                ok=True, detail="secret résolu", probe_path_used=path,
            )
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            log.info(
                "vault.test_connection",
                vault_id=str(vault_id), ok=False,
                status_code=status_code, probe_path_used=path,
            )
            if status_code in (401, 403):
                return VaultTestConnectionResult(
                    ok=False, detail=f"auth refusée ({status_code})",
                    probe_path_used=path,
                )
            if status_code == 404:
                if vault.probe_path is None:
                    return VaultTestConnectionResult(
                        ok=True,
                        detail="auth ok (404 sur __probe__ — secret inexistant attendu)",
                        probe_path_used=path,
                    )
                return VaultTestConnectionResult(
                    ok=False, detail=f"probe_path '{path}' introuvable",
                    probe_path_used=path,
                )
            return VaultTestConnectionResult(
                ok=False, detail=f"erreur SDK : {type(exc).__name__}",
                probe_path_used=path,
            )
```

- [ ] **Step 4: Lancer, doivent passer**

```powershell
uv run pytest tests/unit/services/test_harpocrate_vaults_service_test_connection.py -v
```

Expected : 4 PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/rag/services/harpocrate_vaults.py backend/tests/unit/services/test_harpocrate_vaults_service_test_connection.py
git commit -m "feat(M5c): HarpocrateVaultsService.test_connection (SDK probe)"
```

---

## Task 8: `HarpocrateClientProvider` avec fallback env

**Files:**
- Create: `backend/src/rag/secrets/client_provider.py`
- Create: `backend/tests/unit/secrets/test_client_provider.py`

- [ ] **Step 1: Écrire les tests**

`backend/tests/unit/secrets/test_client_provider.py` :

```python
from __future__ import annotations

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from rag.secrets.client_provider import HarpocrateClientProvider
from rag.secrets.exceptions import VaultNotFoundError
from rag.schemas.harpocrate_vaults import VaultCreateRequest


def _req(**o):
    p = {
        "name": "rag", "label": "Coffre RAG",
        "base_url": "https://harpocrate.yoops.org",
        "api_key_id": "k-001", "api_key": "supersecretvalue123",
        "is_default": True,
    }
    p.update(o)
    return VaultCreateRequest(**p)


@pytest.mark.asyncio
async def test_load_from_db_when_non_empty(db_conn, db_pool, service):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    async with db_conn.transaction():
        await service.create(db_conn, _req(name="dbvault"))

    with patch("rag.secrets.client_provider.HarpocrateVaultClient") as MockClient:
        MockClient.return_value = MagicMock()
        provider = HarpocrateClientProvider(service._settings, service, db_pool)
        client = await provider.get_client("dbvault")
        assert client is not None
        assert await provider.get_default_vault_name() == "dbvault"


@pytest.mark.asyncio
async def test_fallback_env_when_db_empty(db_conn, db_pool, service, monkeypatch):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "envtoken")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://h.env")
    from rag.config import Settings
    settings = Settings()

    with patch("rag.secrets.client_provider.HarpocrateVaultClient") as MockClient:
        MockClient.return_value = MagicMock()
        provider = HarpocrateClientProvider(settings, service, db_pool)
        client = await provider.get_client("rag")
        assert client is not None
        assert await provider.get_default_vault_name() == "rag"


@pytest.mark.asyncio
async def test_get_default_first_alphabetical_in_env_fallback(
    db_conn, db_pool, service, monkeypatch,
):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_ZULU", "t1")
    monkeypatch.setenv("HARPOCRATE_API_URL_ZULU", "https://z")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_ALPHA", "t2")
    monkeypatch.setenv("HARPOCRATE_API_URL_ALPHA", "https://a")
    from rag.config import Settings
    settings = Settings()

    with patch("rag.secrets.client_provider.HarpocrateVaultClient") as MockClient:
        MockClient.return_value = MagicMock()
        provider = HarpocrateClientProvider(settings, service, db_pool)
        assert await provider.get_default_vault_name() == "alpha"


@pytest.mark.asyncio
async def test_unknown_vault_name_raises(db_conn, db_pool, service):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    provider = HarpocrateClientProvider(service._settings, service, db_pool)
    with pytest.raises(VaultNotFoundError):
        await provider.get_client("absent")


@pytest.mark.asyncio
async def test_invalidate_forces_reload(db_conn, db_pool, service):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    async with db_conn.transaction():
        await service.create(db_conn, _req(name="v1"))

    with patch("rag.secrets.client_provider.HarpocrateVaultClient") as MockClient:
        MockClient.return_value = MagicMock()
        provider = HarpocrateClientProvider(service._settings, service, db_pool)
        await provider.get_client("v1")  # load 1
        async with db_conn.transaction():
            await service.create(db_conn, _req(name="v2", api_key_id="k2", is_default=False))
        provider.invalidate()
        client_v2 = await provider.get_client("v2")  # reload
        assert client_v2 is not None


@pytest.mark.asyncio
async def test_default_missing_when_no_is_default_in_db(
    db_conn, db_pool, service,
):
    """Si la table contient des coffres mais aucun is_default=true, default_name=None."""
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    async with db_conn.transaction():
        v = await service.create(db_conn, _req(name="orphan", is_default=True))
    await db_conn.execute(
        "UPDATE harpocrate_vaults SET is_default = false WHERE id = $1", v.id,
    )
    with patch("rag.secrets.client_provider.HarpocrateVaultClient") as MockClient:
        MockClient.return_value = MagicMock()
        provider = HarpocrateClientProvider(service._settings, service, db_pool)
        assert await provider.get_default_vault_name() is None
```

Ajouter dans `conftest.py` une fixture `db_pool` qui partage le pool asyncpg.

- [ ] **Step 2: Lancer, doivent échouer**

```powershell
uv run pytest tests/unit/secrets/test_client_provider.py -v
```

- [ ] **Step 3: Implémenter `backend/src/rag/secrets/client_provider.py`**

```python
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import structlog
from asyncpg import Pool

from rag.config import Settings
from rag.secrets.exceptions import VaultNotFoundError
from rag.secrets.vault import HarpocrateVaultClient

if TYPE_CHECKING:
    from rag.services.harpocrate_vaults import HarpocrateVaultsService

log = structlog.get_logger(__name__)

_TTL_SECONDS = 60


class HarpocrateClientProvider:
    def __init__(
        self,
        settings: Settings,
        vaults_service: "HarpocrateVaultsService",
        db_pool: Pool,
    ) -> None:
        self._settings = settings
        self._service = vaults_service
        self._pool = db_pool
        self._clients: dict[str, HarpocrateVaultClient] = {}
        self._default_name: str | None = None
        self._loaded_at: float = 0.0
        self._invalidated: bool = True
        self._lock = asyncio.Lock()

    def invalidate(self) -> None:
        self._invalidated = True

    async def get_client(self, vault_name: str) -> HarpocrateVaultClient:
        await self._ensure_loaded()
        try:
            return self._clients[vault_name]
        except KeyError as exc:
            raise VaultNotFoundError(vault_name) from exc

    async def get_default_vault_name(self) -> str | None:
        await self._ensure_loaded()
        return self._default_name

    async def _ensure_loaded(self) -> None:
        if (
            not self._invalidated
            and time.monotonic() - self._loaded_at < _TTL_SECONDS
        ):
            return
        async with self._lock:
            if (
                not self._invalidated
                and time.monotonic() - self._loaded_at < _TTL_SECONDS
            ):
                return
            await self._load()
            self._loaded_at = time.monotonic()
            self._invalidated = False

    async def _load(self) -> None:
        async with self._pool.acquire() as conn:
            vaults = await self._service.list_all(conn)
            if vaults:
                clients: dict[str, HarpocrateVaultClient] = {}
                for v in vaults:
                    api_key = await self._service.reveal_api_key(conn, v.id)
                    if api_key is None:
                        continue
                    clients[v.name] = HarpocrateVaultClient(
                        url=v.base_url, token=api_key,
                    )
                self._clients = clients
                self._default_name = next(
                    (v.name for v in vaults if v.is_default), None,
                )
                if self._default_name is None:
                    log.warning(
                        "vault.default_missing", clients_count=len(clients),
                    )
                return

        # Fallback env
        env_clients: dict[str, HarpocrateVaultClient] = {}
        for identifier, cfg in self._settings.harpocrate_api_keys.items():
            name = identifier.lower()
            env_clients[name] = HarpocrateVaultClient(
                url=str(cfg.url).rstrip("/"),
                token=cfg.token.get_secret_value(),
            )
        self._clients = env_clients
        if env_clients:
            self._default_name = min(env_clients.keys())
        else:
            self._default_name = None
```

- [ ] **Step 4: Lancer, doivent passer**

```powershell
uv run pytest tests/unit/secrets/test_client_provider.py -v
```

Expected : 6 PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/rag/secrets/client_provider.py backend/tests/conftest.py backend/tests/unit/secrets/test_client_provider.py
git commit -m "feat(M5c): HarpocrateClientProvider (DB-first + fallback env + TTL)"
```

---

## Task 9: Refactor `SecretResolver` async

**Files:**
- Modify: `backend/src/rag/secrets/resolver.py`
- Modify: `backend/tests/unit/secrets/test_resolver*.py` (renommer + adapter)

- [ ] **Step 1: Écrire le nouveau test (avant refactor)**

Créer `backend/tests/unit/secrets/test_resolver_async.py` :

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.secrets.resolver import SecretResolver
from rag.secrets.exceptions import VaultNotFoundError


@pytest.mark.asyncio
async def test_resolve_ref_calls_provider():
    provider = AsyncMock()
    client = MagicMock()
    client.get_secret.return_value = "the-secret"
    provider.get_client = AsyncMock(return_value=client)

    resolver = SecretResolver(provider, cache_ttl=300)
    value = await resolver.resolve_ref("${vault://rag:openai_key}")
    assert value == "the-secret"
    provider.get_client.assert_awaited_with("rag")
    client.get_secret.assert_called_with("openai_key")


@pytest.mark.asyncio
async def test_resolve_ref_caches():
    provider = AsyncMock()
    client = MagicMock()
    client.get_secret.return_value = "v"
    provider.get_client = AsyncMock(return_value=client)

    resolver = SecretResolver(provider, cache_ttl=300)
    await resolver.resolve_ref("${vault://rag:k}")
    await resolver.resolve_ref("${vault://rag:k}")
    assert client.get_secret.call_count == 1


@pytest.mark.asyncio
async def test_resolve_with_retry_invalidates_on_401():
    provider = AsyncMock()
    client_old = MagicMock()
    client_old.get_secret.side_effect = _Err401()
    client_new = MagicMock()
    client_new.get_secret.return_value = "fresh"
    provider.get_client = AsyncMock(side_effect=[client_old, client_new])
    provider.invalidate = MagicMock()

    resolver = SecretResolver(provider, cache_ttl=300)
    value = await resolver.resolve_with_retry("${vault://rag:k}")
    assert value == "fresh"
    provider.invalidate.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_ref_propagates_vault_not_found():
    provider = AsyncMock()
    provider.get_client = AsyncMock(side_effect=VaultNotFoundError("absent"))
    resolver = SecretResolver(provider, cache_ttl=300)
    with pytest.raises(VaultNotFoundError):
        await resolver.resolve_ref("${vault://absent:k}")


class _Err401(Exception):
    class _R:
        status_code = 401
    def __init__(self):
        self.response = self._R()
```

- [ ] **Step 2: Lancer, doivent échouer (signature actuelle = sync)**

```powershell
uv run pytest tests/unit/secrets/test_resolver_async.py -v
```

- [ ] **Step 3: Refactorer `backend/src/rag/secrets/resolver.py`**

```python
from __future__ import annotations

import time

import structlog

from rag.secrets.client_provider import HarpocrateClientProvider
from rag.secrets.refs import parse_ref

log = structlog.get_logger(__name__)


class SecretResolver:
    def __init__(
        self,
        client_provider: HarpocrateClientProvider,
        *,
        cache_ttl: int = 300,
    ) -> None:
        self._provider = client_provider
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, str]] = {}

    async def resolve_ref(self, ref: str) -> str:
        cached = self._cache.get(ref)
        if cached and time.monotonic() - cached[0] < self._cache_ttl:
            return cached[1]

        vault_name, path = parse_ref(ref)
        client = await self._provider.get_client(vault_name)
        value = client.get_secret(path)
        self._cache[ref] = (time.monotonic(), value)
        return value

    async def resolve_with_retry(self, ref: str) -> str:
        try:
            return await self.resolve_ref(ref)
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == 401:
                log.warning("resolver.retry_on_401", ref=ref)
                self._provider.invalidate()
                self._cache.pop(ref, None)
                return await self.resolve_ref(ref)
            raise
```

- [ ] **Step 4: Supprimer l'ancien fichier de test (s'il existe)**

Identifier les anciens tests :

```powershell
ls tests/unit/secrets/
```

Si `test_resolver.py` existe et utilise l'ancienne signature (`dict[str, VaultClient]` synchrone), le **supprimer** : `git rm tests/unit/secrets/test_resolver.py`. Les nouveaux tests dans `test_resolver_async.py` couvrent le comportement.

- [ ] **Step 5: Lancer, doivent passer**

```powershell
uv run pytest tests/unit/secrets/test_resolver_async.py -v
```

Expected : 4 PASS.

- [ ] **Step 6: Adapter tout caller de `resolver.resolve_ref(...)` sync → `await resolver.resolve_ref(...)`**

```powershell
uv run grep -rn "resolver.resolve_ref" src/
```

Pour chaque occurrence : transformer en `await resolver.resolve_ref(...)`. Vérifier que la fonction enclosante est `async def`. Si non, propager.

Sites attendus : `services/oidc.py`, `indexer/real.py`, `sync/executor.py` essentiellement (à confirmer par grep).

- [ ] **Step 7: Lancer toute la suite, identifier les casses**

```powershell
uv run pytest tests/ -v
```

Corriger les tests existants qui mockent l'ancienne signature de `SecretResolver`. Ajouter `await` partout où nécessaire.

- [ ] **Step 8: Commit**

```powershell
git add backend/src/rag/secrets/resolver.py backend/tests/unit/secrets/test_resolver_async.py
git add -A  # pour inclure les call-sites adaptés et les anciens tests supprimés
git commit -m "refactor(M5c): SecretResolver async + consomme HarpocrateClientProvider"
```

---

## Task 10: Bootstrap `seed_vaults_from_env_if_empty`

**Files:**
- Create: `backend/src/rag/secrets/bootstrap.py`
- Create: `backend/tests/api/test_seed_bootstrap.py`

- [ ] **Step 1: Écrire les tests**

`backend/tests/api/test_seed_bootstrap.py` :

```python
from __future__ import annotations

import pytest

from rag.secrets.bootstrap import seed_vaults_from_env_if_empty


@pytest.mark.asyncio
async def test_seed_creates_vault_named_rag(
    db_conn, db_pool, service, monkeypatch,
):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "envsecret")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://h.env")
    monkeypatch.setenv("HARPOCRATE_DEK", "x" * 64)
    from rag.config import Settings
    settings = Settings()
    from rag.services.harpocrate_vaults import HarpocrateVaultsService
    svc = HarpocrateVaultsService(settings)

    count = await seed_vaults_from_env_if_empty(
        settings=settings, pool=db_pool, vaults_service=svc,
    )
    assert count == 1
    v = await svc.get_by_name(db_conn, "rag")
    assert v is not None
    assert v.is_default is True
    assert v.api_key_id == "env:RAG"


@pytest.mark.asyncio
async def test_seed_skipped_when_db_non_empty(
    db_conn, db_pool, service, monkeypatch,
):
    from rag.schemas.harpocrate_vaults import VaultCreateRequest
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    async with db_conn.transaction():
        await service.create(
            db_conn,
            VaultCreateRequest(
                name="existing", label="X",
                base_url="https://x", api_key_id="k1",
                api_key="secret12345678", is_default=True,
            ),
        )
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "envsecret")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://h.env")
    from rag.config import Settings
    settings = Settings()

    count = await seed_vaults_from_env_if_empty(
        settings=settings, pool=db_pool, vaults_service=service,
    )
    assert count == 0


@pytest.mark.asyncio
async def test_seed_skipped_when_env_empty(
    db_conn, db_pool, service, monkeypatch,
):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    monkeypatch.delenv("HARPOCRATE_API_TOKEN_RAG", raising=False)
    monkeypatch.delenv("HARPOCRATE_API_URL_RAG", raising=False)
    monkeypatch.setenv("HARPOCRATE_DEK", "x" * 64)
    from rag.config import Settings
    settings = Settings()
    from rag.services.harpocrate_vaults import HarpocrateVaultsService
    svc = HarpocrateVaultsService(settings)

    count = await seed_vaults_from_env_if_empty(
        settings=settings, pool=db_pool, vaults_service=svc,
    )
    assert count == 0


@pytest.mark.asyncio
async def test_seed_aborted_when_dek_missing(
    db_conn, db_pool, service, monkeypatch, caplog,
):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "envsecret")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://h.env")
    monkeypatch.delenv("HARPOCRATE_DEK", raising=False)
    from rag.config import Settings
    settings = Settings()
    from rag.services.harpocrate_vaults import HarpocrateVaultsService
    svc = HarpocrateVaultsService(settings)

    count = await seed_vaults_from_env_if_empty(
        settings=settings, pool=db_pool, vaults_service=svc,
    )
    assert count == 0
```

- [ ] **Step 2: Lancer, doivent échouer (module inexistant)**

```powershell
uv run pytest tests/api/test_seed_bootstrap.py -v
```

- [ ] **Step 3: Implémenter `backend/src/rag/secrets/bootstrap.py`**

```python
from __future__ import annotations

import structlog
from asyncpg import Pool

from rag.config import Settings
from rag.schemas.harpocrate_vaults import VaultCreateRequest
from rag.services.harpocrate_vaults import HarpocrateVaultsService

log = structlog.get_logger(__name__)


async def seed_vaults_from_env_if_empty(
    *,
    settings: Settings,
    pool: Pool,
    vaults_service: HarpocrateVaultsService,
) -> int:
    async with pool.acquire() as conn:
        existing = await vaults_service.list_all(conn)
        if existing:
            log.info("vault.seed.skipped", reason="table non vide", count=len(existing))
            return 0

        if not settings.harpocrate_api_keys:
            log.info("vault.seed.skipped", reason="env vide")
            return 0

        if settings.harpocrate_dek is None:
            log.error("vault.seed.aborted", reason="HARPOCRATE_DEK manquant")
            return 0

        identifiers = sorted(settings.harpocrate_api_keys.keys())
        default_id = identifiers[0]
        created = 0
        async with conn.transaction():
            for identifier in identifiers:
                cfg = settings.harpocrate_api_keys[identifier]
                req = VaultCreateRequest(
                    name=identifier.lower(),
                    label=f"Coffre {identifier} (seed env)",
                    base_url=str(cfg.url).rstrip("/"),
                    api_key_id=f"env:{identifier}",
                    api_key=cfg.token.get_secret_value(),
                    probe_path=None,
                    is_default=(identifier == default_id),
                )
                await vaults_service.create(conn, req)
                created += 1
                log.info("vault.seed.created", name=req.name, is_default=req.is_default)
        return created
```

- [ ] **Step 4: Lancer, doivent passer**

```powershell
uv run pytest tests/api/test_seed_bootstrap.py -v
```

Expected : 4 PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/rag/secrets/bootstrap.py backend/tests/api/test_seed_bootstrap.py
git commit -m "feat(M5c): seed_vaults_from_env_if_empty au lifespan"
```

---

## Task 11: Router `/api/admin/harpocrate-vaults` (9 endpoints)

**Files:**
- Create: `backend/src/rag/api/admin/harpocrate_vaults.py`
- Create: `backend/tests/api/test_admin_harpocrate_vaults.py`

- [ ] **Step 1: Écrire les tests d'intégration**

`backend/tests/api/test_admin_harpocrate_vaults.py` :

```python
from __future__ import annotations

import pytest


def _payload(**o):
    p = {
        "name": "rag", "label": "Coffre RAG",
        "base_url": "https://harpocrate.yoops.org",
        "api_key_id": "k-001", "api_key": "supersecretvalue123",
        "is_default": True,
    }
    p.update(o)
    return p


@pytest.fixture
def auth_headers(settings_with_dek):
    return {"Authorization": f"Bearer {settings_with_dek.rag_master_key.get_secret_value()}"}


def test_create_returns_201_no_api_key_in_response(client, db_conn, auth_headers):
    db_conn.execute("DELETE FROM harpocrate_vaults")
    r = client.post("/api/admin/harpocrate-vaults", json=_payload(), headers=auth_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "rag"
    assert '"api_key":' not in r.text


def test_create_duplicate_name_returns_409(client, db_conn, auth_headers):
    db_conn.execute("DELETE FROM harpocrate_vaults")
    client.post("/api/admin/harpocrate-vaults", json=_payload(), headers=auth_headers)
    r = client.post(
        "/api/admin/harpocrate-vaults",
        json=_payload(api_key_id="k-002", is_default=False),
        headers=auth_headers,
    )
    assert r.status_code == 409


def test_create_invalid_slug_returns_422(client, auth_headers):
    r = client.post(
        "/api/admin/harpocrate-vaults",
        json=_payload(name="BAD NAME"),
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_list_returns_summaries_without_api_key(client, db_conn, auth_headers):
    db_conn.execute("DELETE FROM harpocrate_vaults")
    client.post("/api/admin/harpocrate-vaults", json=_payload(), headers=auth_headers)
    r = client.get("/api/admin/harpocrate-vaults", headers=auth_headers)
    assert r.status_code == 200
    assert '"api_key":' not in r.text
    assert len(r.json()) == 1


def test_get_by_id_returns_summary(client, db_conn, auth_headers):
    db_conn.execute("DELETE FROM harpocrate_vaults")
    created = client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=auth_headers,
    ).json()
    r = client.get(f"/api/admin/harpocrate-vaults/{created['id']}", headers=auth_headers)
    assert r.status_code == 200


def test_get_nonexistent_returns_404(client, auth_headers):
    r = client.get(
        "/api/admin/harpocrate-vaults/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_patch_name_field_rejected_422(client, db_conn, auth_headers):
    db_conn.execute("DELETE FROM harpocrate_vaults")
    created = client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=auth_headers,
    ).json()
    r = client.patch(
        f"/api/admin/harpocrate-vaults/{created['id']}",
        json={"name": "newname"},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_patch_is_default_field_rejected_422(client, db_conn, auth_headers):
    db_conn.execute("DELETE FROM harpocrate_vaults")
    created = client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=auth_headers,
    ).json()
    r = client.patch(
        f"/api/admin/harpocrate-vaults/{created['id']}",
        json={"is_default": False},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_patch_updates_label(client, db_conn, auth_headers):
    db_conn.execute("DELETE FROM harpocrate_vaults")
    created = client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=auth_headers,
    ).json()
    r = client.patch(
        f"/api/admin/harpocrate-vaults/{created['id']}",
        json={"label": "Renommé"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["label"] == "Renommé"


def test_delete_default_alone_returns_204(client, db_conn, auth_headers):
    db_conn.execute("DELETE FROM harpocrate_vaults")
    created = client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=auth_headers,
    ).json()
    r = client.delete(
        f"/api/admin/harpocrate-vaults/{created['id']}", headers=auth_headers,
    )
    assert r.status_code == 204


def test_delete_default_with_others_returns_409(client, db_conn, auth_headers):
    db_conn.execute("DELETE FROM harpocrate_vaults")
    default = client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=auth_headers,
    ).json()
    client.post(
        "/api/admin/harpocrate-vaults",
        json=_payload(name="second", api_key_id="k-002", is_default=False),
        headers=auth_headers,
    )
    r = client.delete(
        f"/api/admin/harpocrate-vaults/{default['id']}", headers=auth_headers,
    )
    assert r.status_code == 409


def test_set_default_swaps_atomically(client, db_conn, auth_headers):
    db_conn.execute("DELETE FROM harpocrate_vaults")
    first = client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=auth_headers,
    ).json()
    second = client.post(
        "/api/admin/harpocrate-vaults",
        json=_payload(name="second", api_key_id="k-002", is_default=False),
        headers=auth_headers,
    ).json()
    r = client.post(
        f"/api/admin/harpocrate-vaults/{second['id']}/set-default",
        headers=auth_headers,
    )
    assert r.status_code == 200
    refreshed_first = client.get(
        f"/api/admin/harpocrate-vaults/{first['id']}", headers=auth_headers,
    ).json()
    assert refreshed_first["is_default"] is False
    assert r.json()["is_default"] is True


def test_rotate_api_key(client, db_conn, auth_headers):
    db_conn.execute("DELETE FROM harpocrate_vaults")
    created = client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=auth_headers,
    ).json()
    r = client.post(
        f"/api/admin/harpocrate-vaults/{created['id']}/rotate-api-key",
        json={"api_key_id": "k-002", "api_key": "newsecretXYZ987"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["api_key_id"] == "k-002"

    reveal = client.get(
        f"/api/admin/harpocrate-vaults/{created['id']}/api-key",
        headers=auth_headers,
    )
    assert reveal.json()["api_key"] == "newsecretXYZ987"


def test_reveal_api_key_endpoint(client, db_conn, auth_headers):
    db_conn.execute("DELETE FROM harpocrate_vaults")
    created = client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=auth_headers,
    ).json()
    r = client.get(
        f"/api/admin/harpocrate-vaults/{created['id']}/api-key",
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["api_key"] == "supersecretvalue123"


def test_anonymous_returns_401(client):
    r = client.get("/api/admin/harpocrate-vaults")
    assert r.status_code == 401
```

(Le test `test_test_connection_*` est traité unitairement dans Task 7 — le test d'intégration HTTP serait redondant et nécessiterait un Harpocrate réel ou un mock intrusif au niveau du wiring.)

- [ ] **Step 2: Lancer, doivent échouer**

```powershell
uv run pytest tests/api/test_admin_harpocrate_vaults.py -v
```

- [ ] **Step 3: Implémenter `backend/src/rag/api/admin/harpocrate_vaults.py`**

```python
from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from asyncpg import Connection

from rag.auth.dependencies import (
    require_master_key_or_oidc_role,
    get_current_actor,
)
from rag.db.pool import get_connection
from rag.schemas.harpocrate_vaults import (
    VaultCreateRequest,
    VaultRevealApiKeyResponse,
    VaultRotateApiKeyRequest,
    VaultSummary,
    VaultTestConnectionResult,
    VaultUpdateRequest,
)
from rag.secrets.exceptions import (
    VaultNameAlreadyExistsError,
    VaultNotFoundError,
)
from rag.services.harpocrate_vaults import HarpocrateVaultsService

log = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/admin/harpocrate-vaults",
    tags=["admin-harpocrate-vaults"],
    dependencies=[Depends(require_master_key_or_oidc_role("rag-admin"))],
)


def get_vaults_service(request: Request) -> HarpocrateVaultsService:
    return request.app.state.vaults_service


@router.get("", response_model=list[VaultSummary])
async def list_vaults(
    conn: Connection = Depends(get_connection),
    svc: HarpocrateVaultsService = Depends(get_vaults_service),
) -> list[VaultSummary]:
    return await svc.list_all(conn)


@router.post("", status_code=201, response_model=VaultSummary)
async def create_vault(
    req: VaultCreateRequest,
    conn: Connection = Depends(get_connection),
    svc: HarpocrateVaultsService = Depends(get_vaults_service),
    actor: str = Depends(get_current_actor),
) -> VaultSummary:
    try:
        async with conn.transaction():
            v = await svc.create(conn, req)
    except VaultNameAlreadyExistsError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    log.info("vault.created.http", vault_id=str(v.id), actor=actor)
    return v


@router.get("/{vault_id}", response_model=VaultSummary)
async def get_vault(
    vault_id: UUID,
    conn: Connection = Depends(get_connection),
    svc: HarpocrateVaultsService = Depends(get_vaults_service),
) -> VaultSummary:
    v = await svc.get_by_id(conn, vault_id)
    if v is None:
        raise HTTPException(404, "vault not found")
    return v


@router.patch("/{vault_id}", response_model=VaultSummary)
async def update_vault(
    vault_id: UUID,
    req: VaultUpdateRequest,
    conn: Connection = Depends(get_connection),
    svc: HarpocrateVaultsService = Depends(get_vaults_service),
    actor: str = Depends(get_current_actor),
) -> VaultSummary:
    v = await svc.update(conn, vault_id, req)
    if v is None:
        raise HTTPException(404, "vault not found")
    log.info("vault.updated.http", vault_id=str(v.id), actor=actor)
    return v


@router.delete("/{vault_id}", status_code=204)
async def delete_vault(
    vault_id: UUID,
    conn: Connection = Depends(get_connection),
    svc: HarpocrateVaultsService = Depends(get_vaults_service),
    actor: str = Depends(get_current_actor),
) -> None:
    target = await svc.get_by_id(conn, vault_id)
    if target is None:
        raise HTTPException(404, "vault not found")
    if target.is_default:
        others = await svc.list_all(conn)
        if len(others) > 1:
            raise HTTPException(
                409,
                "promouvoir un autre coffre via set-default avant de supprimer le default",
            )
    deleted = await svc.delete(conn, vault_id)
    if not deleted:
        raise HTTPException(404, "vault not found")
    log.info("vault.deleted.http", vault_id=str(vault_id), actor=actor)


@router.post("/{vault_id}/rotate-api-key", response_model=VaultSummary)
async def rotate_api_key(
    vault_id: UUID,
    req: VaultRotateApiKeyRequest,
    conn: Connection = Depends(get_connection),
    svc: HarpocrateVaultsService = Depends(get_vaults_service),
    actor: str = Depends(get_current_actor),
) -> VaultSummary:
    v = await svc.rotate_api_key(conn, vault_id, req)
    if v is None:
        raise HTTPException(404, "vault not found")
    log.info("vault.api_key_rotated.http", vault_id=str(v.id), actor=actor)
    return v


@router.post("/{vault_id}/set-default", response_model=VaultSummary)
async def set_default(
    vault_id: UUID,
    conn: Connection = Depends(get_connection),
    svc: HarpocrateVaultsService = Depends(get_vaults_service),
    actor: str = Depends(get_current_actor),
) -> VaultSummary:
    v = await svc.set_default(conn, vault_id)
    if v is None:
        raise HTTPException(404, "vault not found")
    log.info("vault.default_changed.http", vault_id=str(v.id), actor=actor)
    return v


@router.post("/{vault_id}/test-connection", response_model=VaultTestConnectionResult)
async def test_connection(
    vault_id: UUID,
    conn: Connection = Depends(get_connection),
    svc: HarpocrateVaultsService = Depends(get_vaults_service),
) -> VaultTestConnectionResult:
    try:
        return await svc.test_connection(conn, vault_id)
    except VaultNotFoundError as exc:
        raise HTTPException(404, "vault not found") from exc


@router.get("/{vault_id}/api-key", response_model=VaultRevealApiKeyResponse)
async def reveal_api_key(
    vault_id: UUID,
    conn: Connection = Depends(get_connection),
    svc: HarpocrateVaultsService = Depends(get_vaults_service),
    actor: str = Depends(get_current_actor),
) -> VaultRevealApiKeyResponse:
    v = await svc.get_by_id(conn, vault_id)
    if v is None:
        raise HTTPException(404, "vault not found")
    api_key = await svc.reveal_api_key(conn, vault_id)
    log.warning("vault.reveal", vault_id=str(vault_id), actor=actor)
    return VaultRevealApiKeyResponse(
        id=v.id, api_key_id=v.api_key_id, api_key=api_key or "",
    )
```

- [ ] **Step 4: Brancher le router dans `main.py`**

Dans `backend/src/rag/main.py`, après les autres `include_router` :

```python
from rag.api.admin.harpocrate_vaults import router as harpocrate_vaults_router
app.include_router(harpocrate_vaults_router)
```

- [ ] **Step 5: Câbler `app.state.vaults_service` (provisoire — sera finalisé en Task 14)**

Dans le lifespan, ajouter (avant le `yield`) :

```python
from rag.services.harpocrate_vaults import HarpocrateVaultsService
app.state.vaults_service = HarpocrateVaultsService(settings)
```

- [ ] **Step 6: Lancer les tests**

```powershell
uv run pytest tests/api/test_admin_harpocrate_vaults.py -v
```

Expected : ~15 PASS.

- [ ] **Step 7: Commit**

```powershell
git add backend/src/rag/api/admin/harpocrate_vaults.py backend/src/rag/main.py backend/tests/api/test_admin_harpocrate_vaults.py
git commit -m "feat(M5c): router /api/admin/harpocrate-vaults (9 endpoints)"
```

---

## Task 12: Refactor 7 sites métier pour `build_ref(default_vault_name, path)`

**Files:**
- Modify: `backend/src/rag/services/workspaces.py`
- Modify: `backend/src/rag/services/sources.py`
- Modify: `backend/src/rag/services/jobs.py`
- Modify: `backend/src/rag/services/mcp.py`
- Modify: `backend/src/rag/services/oidc.py`
- Modify: `backend/src/rag/indexer/real.py`
- Modify: `backend/src/rag/sync/executor.py`
- Modify: tous les routers qui appellent ces services (workspaces, sources, jobs, mcp)

- [ ] **Step 1: Inventaire des call-sites**

```powershell
uv run grep -rn 'vault://rag' src/
uv run grep -rn '_to_vault_ref' src/
```

Récupérer la liste précise des fichiers et lignes.

- [ ] **Step 2: Pour chaque service, modifier la signature et l'implémentation**

Exemple `services/workspaces.py:41` :

```python
# AVANT
def _to_vault_ref(logical_key: str, vault_id: str = "rag") -> str:
    return f"${{vault://{vault_id}:{logical_key}}}"

async def create(conn, req: WorkspaceCreateRequest) -> WorkspaceSummary:
    ...
    if req.indexer.api_key:
        api_key_ref = _to_vault_ref("openai_embedding_key")
```

```python
# APRÈS
from rag.secrets.refs import build_ref

def _to_vault_ref(logical_key: str, vault_name: str) -> str:
    return build_ref(vault_name, logical_key)

async def create(
    conn, req: WorkspaceCreateRequest, *, default_vault_name: str,
) -> WorkspaceSummary:
    ...
    if req.indexer.api_key:
        api_key_ref = _to_vault_ref("openai_embedding_key", default_vault_name)
```

Refaire le même pattern pour `sources.py:29`, `jobs.py:94`, `mcp.py:130`, `indexer/real.py:24`, `sync/executor.py:114`, `oidc.py:329`.

- [ ] **Step 3: Ajouter un helper dans les routers pour résoudre `default_vault_name`**

Dans chaque router consommateur, exemple `api/admin/workspaces.py` :

```python
from rag.secrets.client_provider import HarpocrateClientProvider


def get_client_provider(request: Request) -> HarpocrateClientProvider:
    return request.app.state.client_provider


async def _resolve_default_vault(
    provider: HarpocrateClientProvider, requires_secret: bool,
) -> str | None:
    name = await provider.get_default_vault_name()
    if requires_secret and name is None:
        raise HTTPException(503, "aucun coffre Harpocrate configuré")
    return name


@router.post("/workspaces", status_code=201)
async def create_workspace(
    req: WorkspaceCreateRequest,
    conn: Connection = Depends(get_connection),
    provider: HarpocrateClientProvider = Depends(get_client_provider),
):
    default_name = await _resolve_default_vault(provider, req.requires_secret())
    async with conn.transaction():
        return await workspaces_service.create(
            conn, req, default_vault_name=default_name,
        )
```

`req.requires_secret()` retourne `True` si le DTO contient un `api_key` à stocker (à ajouter sur `WorkspaceCreateRequest` et équivalents).

- [ ] **Step 4: Worker `sync/executor.py`**

Le worker reçoit `client_provider` à la construction (déjà fait en Task 14). À chaque endroit qui build une ref, appeler `await self._client_provider.get_default_vault_name()` et raise/skip si `None`.

- [ ] **Step 5: Lancer toute la suite, identifier les casses**

```powershell
uv run pytest tests/ -v
```

Adapter les tests existants : passer `default_vault_name="rag"` aux appels de services concernés. Ajouter une fixture commune si besoin.

- [ ] **Step 6: Vérifier qu'aucun `vault://rag` hardcodé ne reste**

```powershell
uv run grep -rn 'vault://rag' src/
```

Expected : 0 occurrence (sauf dans les docstrings/commentaires explicatifs).

- [ ] **Step 7: Commit**

```powershell
git add -A
git commit -m "refactor(M5c): 7 sites métier consomment build_ref(default_vault_name)"
```

---

## Task 13: Câblage complet du lifespan `main.py`

**Files:**
- Modify: `backend/src/rag/main.py`
- Create: `backend/tests/api/test_lifespan_empty_state.py`

- [ ] **Step 1: Écrire le test du boot en état vide**

`backend/tests/api/test_lifespan_empty_state.py` :

```python
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_app_boots_with_empty_db_and_empty_env(
    db_conn, monkeypatch,
):
    await db_conn.execute("DELETE FROM harpocrate_vaults")
    monkeypatch.delenv("HARPOCRATE_API_TOKEN_RAG", raising=False)
    monkeypatch.delenv("HARPOCRATE_API_URL_RAG", raising=False)
    monkeypatch.setenv("HARPOCRATE_DEK", "x" * 64)

    from rag.main import build_app
    app = build_app()
    # smoke : la création de l'app ne lève pas
    assert app is not None


def test_workspace_create_requires_vault_returns_503(
    client, db_conn, auth_headers, monkeypatch,
):
    """Si DB vide et env vide, création de workspace nécessitant un secret → 503."""
    db_conn.execute("DELETE FROM harpocrate_vaults")
    monkeypatch.delenv("HARPOCRATE_API_TOKEN_RAG", raising=False)
    # supposer qu'un endpoint /api/admin/workspaces existe pour le test
    r = client.post(
        "/api/admin/workspaces",
        json={
            "slug": "demo",
            "label": "Demo",
            "indexer": {"engine": "openai", "api_key": "value"},
        },
        headers=auth_headers,
    )
    assert r.status_code == 503
```

- [ ] **Step 2: Lancer, doit échouer (lifespan pas complet)**

```powershell
uv run pytest tests/api/test_lifespan_empty_state.py -v
```

- [ ] **Step 3: Finaliser le lifespan dans `main.py`**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from rag.config import get_settings
from rag.db.pool import create_pool, run_migrations
from rag.secrets.bootstrap import seed_vaults_from_env_if_empty
from rag.secrets.client_provider import HarpocrateClientProvider
from rag.secrets.resolver import SecretResolver
from rag.services.harpocrate_vaults import HarpocrateVaultsService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db_pool = await create_pool(settings.database_url.get_secret_value())
    await run_migrations(db_pool)

    vaults_service = HarpocrateVaultsService(settings)
    client_provider = HarpocrateClientProvider(settings, vaults_service, db_pool)
    vaults_service.bind_client_provider(client_provider)

    await seed_vaults_from_env_if_empty(
        settings=settings, pool=db_pool, vaults_service=vaults_service,
    )

    resolver = SecretResolver(client_provider, cache_ttl=settings.secret_cache_ttl)

    app.state.db_pool = db_pool
    app.state.vaults_service = vaults_service
    app.state.client_provider = client_provider
    app.state.resolver = resolver

    # SyncExecutor reçoit le client_provider
    from rag.sync.executor import SyncExecutor
    sync_executor = SyncExecutor(
        db_pool=db_pool, resolver=resolver, client_provider=client_provider,
    )
    app.state.sync_executor = sync_executor
    import asyncio
    sync_task = asyncio.create_task(sync_executor.run())

    try:
        yield
    finally:
        sync_task.cancel()
        await db_pool.close()


def build_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    # include_routers : health, admin/secrets, admin/workspaces, admin/sources,
    # admin/jobs, admin/mcp, admin/oidc, auth, push, search, admin/harpocrate_vaults
    return app
```

- [ ] **Step 4: Lancer les tests**

```powershell
uv run pytest tests/api/test_lifespan_empty_state.py -v
```

- [ ] **Step 5: Lancer toute la suite**

```powershell
uv run pytest tests/ -v
```

Expected : tout vert. Si rouge : adapter au cas par cas (souvent fixture conftest à mettre à jour).

- [ ] **Step 6: Commit**

```powershell
git add backend/src/rag/main.py backend/tests/api/test_lifespan_empty_state.py
git commit -m "feat(M5c): lifespan câble vaults_service + client_provider + seed + resolver async"
```

---

## Task 14: Documentation `.env.example` + smoke manuel + ruff

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Mettre à jour `.env.example`**

Ajouter dans `.env.example` (ou créer la section si absente) :

```bash
# --- Harpocrate (M5c) ---
# Passphrase pgcrypto pour chiffrer les api_keys en DB.
# OBLIGATOIRE dès qu'un coffre est créé via /api/admin/harpocrate-vaults.
# Doubler tout $ en $$ si déposé dans un fichier consommé via docker-compose env_file.
# Minimum 32 caractères.
HARPOCRATE_DEK=replace-me-with-a-32-plus-chars-passphrase

# --- Fallback env (optionnel, rétrocompat M4/M5a/M5b) ---
# Si présents au boot et table harpocrate_vaults vide → seed automatique.
# Le coffre seedé prend name=<identifier en minuscule> → garder RAG pour
# préserver les refs ${vault://rag:...} déjà semées.
HARPOCRATE_API_TOKEN_RAG=<token>
HARPOCRATE_API_URL_RAG=https://harpocrate.yoops.org
```

- [ ] **Step 2: Ruff lint + format**

```powershell
cd backend
uv run ruff check src/ tests/ --fix
uv run ruff format src/ tests/
```

Expected : 0 erreurs résiduelles.

- [ ] **Step 3: Smoke manuel via curl**

Lancer le backend localement :

```powershell
uv run uvicorn agflow.main:app --reload
```

Dans un autre terminal (PowerShell) :

```powershell
$key = $env:RAG_MASTER_KEY
$h = @{ Authorization = "Bearer $key"; "Content-Type" = "application/json" }

# Create
Invoke-RestMethod -Uri http://localhost:8000/api/admin/harpocrate-vaults `
  -Method POST -Headers $h `
  -Body (@{
    name = "smoke"; label = "Smoke"; base_url = "https://harpocrate.yoops.org"
    api_key_id = "k-smoke"; api_key = "smokevalue12345"; is_default = $false
  } | ConvertTo-Json)

# List
Invoke-RestMethod -Uri http://localhost:8000/api/admin/harpocrate-vaults -Headers $h

# Reveal (audit log dans Loki)
$id = (Invoke-RestMethod -Uri http://localhost:8000/api/admin/harpocrate-vaults -Headers $h)[0].id
Invoke-RestMethod -Uri "http://localhost:8000/api/admin/harpocrate-vaults/$id/api-key" -Headers $h

# Delete
Invoke-RestMethod -Uri "http://localhost:8000/api/admin/harpocrate-vaults/$id" -Method DELETE -Headers $h
```

Expected : create renvoie 201, list montre l'entrée, reveal donne `api_key=smokevalue12345`, delete renvoie 204.

- [ ] **Step 4: Commit final**

```powershell
git add .env.example
git commit -m "docs(M5c): .env.example HARPOCRATE_DEK + seed env documentation"
```

- [ ] **Step 5: Déploiement LXC 303**

Conforme à `MEMORY.md → deployment-test-workflow.md` :

```powershell
git push origin dev
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && ./dev-deploy.sh'"
```

Smoke distant identique au step 3 avec l'URL publique.

- [ ] **Step 6: Tag**

```powershell
git tag m5c-backend-done
git push origin m5c-backend-done
```

---

## Self-Review

### Couverture spec → tâches

| Section spec | Tâche(s) couvrante(s) |
|---|---|
| §4 Schéma SQL | Task 2 |
| §5 HARPOCRATE_DEK | Task 1 |
| §6 Schemas Pydantic | Task 4 |
| §7 Service CRUD | Tasks 5, 6 |
| §7 test_connection | Task 7 |
| §8 Router | Task 11 |
| §9 Helpers refs | Task 3 |
| §10 ClientProvider | Task 8 |
| §11 Resolver async | Task 9 |
| §12 Refactor 7 sites | Task 12 |
| §13 Seed bootstrap | Task 10 |
| §14 Lifespan | Task 13 |
| §16 Events structlog | Couverts dans tasks 5, 6, 7, 8, 10, 11 |
| §17 Tests | Couverts par chaque task |
| §18 Pièges | Adressés inline (UUID Python task 5, model_dump task 6, '"api_key":' task 11, $$ task 14, str pour base_url task 4, probe_path validations task 4) |
| §20 Critères complétion | Couverts en task 14 (smoke + tag) |

### Placeholder scan

Aucun "TBD", "TODO", "implement later". Toutes les méthodes ont un corps complet ou un test rouge attendu.

### Cohérence types/noms

- `HarpocrateVaultsService` cohérent entre tasks 5/6/7/8/10/11/13
- `HarpocrateClientProvider.get_default_vault_name()` cohérent entre tasks 8/12/13
- `build_ref` / `parse_ref` cohérent entre tasks 3/9/12
- `default_vault_name` propagé en kwarg-only partout (task 12)

### Bite-sized check

Aucune tâche ne fait > 5 sous-étapes write-test/run-fails/impl/run-passes/commit. Les tâches 8 et 11 sont volumineuses en LOC mais restent un seul commit logique (le client_provider est un composant atomique, le router est un seul fichier).
