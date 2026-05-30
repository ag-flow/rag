# SSH Keys Vault — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un onglet SSH dans les coffres Harpocrate permettant d'importer ou de générer des paires de clés SSH (Ed25519, RSA-4096, ECDSA-256) avec clé privée dans Harpocrate et clé publique en DB.

**Architecture:** Nouvelle table `ssh_keys` (migration 028), service autonome miroir de `git_credentials`, router FastAPI, lib `cryptography` pour la génération. Frontend : `VaultSshTab` + deux dialogs (import/génération) + onglet dans `VaultDetailPanel`.

**Tech Stack:** Python 3.12 / asyncpg / cryptography / FastAPI — React 18 / TypeScript strict / TanStack Query / shadcn/ui / i18next

---

## Structure des fichiers

### Backend (créer)
- `backend/migrations/028_ssh_keys.sql`
- `backend/src/rag/schemas/ssh_keys.py`
- `backend/src/rag/services/ssh_keys.py`
- `backend/src/rag/api/admin_ssh_keys.py`
- `backend/tests/integration/test_services_ssh_keys.py`

### Backend (modifier)
- `backend/pyproject.toml` — ajouter `cryptography>=43.0`
- `backend/src/rag/main.py` — enregistrer le router

### Frontend (créer)
- `frontend/src/pages/harpocrate/VaultSshTab.tsx`
- `frontend/src/pages/harpocrate/ImportSshKeyDialog.tsx`
- `frontend/src/pages/harpocrate/GenerateSshKeyDialog.tsx`

### Frontend (modifier)
- `frontend/src/lib/harpocrate-vaults.types.ts`
- `frontend/src/lib/harpocrate-vaults.ts`
- `frontend/src/hooks/useHarpocrateVaults.ts`
- `frontend/src/i18n/fr/harpocrate.json`
- `frontend/src/i18n/en/harpocrate.json`
- `frontend/src/pages/harpocrate/VaultDetailPanel.tsx`

---

## Task 1 : Migration + dépendance cryptography

**Files:**
- Create: `backend/migrations/028_ssh_keys.sql`
- Modify: `backend/pyproject.toml`

- [ ] **Créer la migration**

```sql
-- backend/migrations/028_ssh_keys.sql
-- Migration 028 — clés SSH dans les coffres Harpocrate

CREATE TABLE ssh_keys (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_id               TEXT NOT NULL,
    name                 TEXT NOT NULL,
    key_type             TEXT NOT NULL,
    public_key           TEXT NOT NULL,
    passphrase_protected BOOLEAN NOT NULL DEFAULT false,
    vault_id             UUID NOT NULL REFERENCES harpocrate_vaults(id) ON DELETE RESTRICT,
    harpo_path           TEXT NOT NULL,
    created_at           TIMESTAMPTZ DEFAULT now(),
    UNIQUE (vault_id, key_id)
);
```

- [ ] **Ajouter la dépendance cryptography dans `backend/pyproject.toml`**

Dans le bloc `dependencies`, ajouter après `"pyyaml>=6.0.3",` :

```toml
    "cryptography>=43.0",
```

- [ ] **Synchroniser les dépendances**

```bash
cd backend && uv sync
```

Résultat attendu : `cryptography` installé sans erreur.

- [ ] **Commit**

```bash
git add backend/migrations/028_ssh_keys.sql backend/pyproject.toml
git commit -m "feat(db): migration 028 ssh_keys + dep cryptography"
```

---

## Task 2 : Schemas

**Files:**
- Create: `backend/src/rag/schemas/ssh_keys.py`

- [ ] **Créer `backend/src/rag/schemas/ssh_keys.py`**

```python
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_KEY_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

SshKeyType = Literal["ed25519", "rsa-4096", "ecdsa-256"]


class SshKeyImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    private_key: str = Field(min_length=1)
    public_key: str = Field(min_length=1)
    passphrase: str | None = Field(default=None)

    @field_validator("key_id")
    @classmethod
    def _v_key_id(cls, v: str) -> str:
        if not _KEY_ID_RE.match(v):
            raise ValueError("key_id doit matcher ^[a-zA-Z0-9_-]+$")
        return v


class SshKeyGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    key_type: SshKeyType

    @field_validator("key_id")
    @classmethod
    def _v_key_id(cls, v: str) -> str:
        if not _KEY_ID_RE.match(v):
            raise ValueError("key_id doit matcher ^[a-zA-Z0-9_-]+$")
        return v


class SshKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key_id: str
    name: str
    key_type: str
    public_key: str
    passphrase_protected: bool
    harpo_path: str
    created_at: datetime
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/schemas/ssh_keys.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/schemas/ssh_keys.py
git commit -m "feat(schemas): SshKeyImport + SshKeyGenerate + SshKeyOut"
```

---

## Task 3 : Service ssh_keys (TDD)

**Files:**
- Create: `backend/src/rag/services/ssh_keys.py`
- Create: `backend/tests/integration/test_services_ssh_keys.py`

- [ ] **Écrire les tests (rouge)**

```python
# backend/tests/integration/test_services_ssh_keys.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.schemas.ssh_keys import SshKeyGenerate, SshKeyImport
from rag.services.ssh_keys import (
    DuplicateSshKeyError,
    delete_ssh_key,
    generate_ssh_key,
    import_ssh_key,
    list_ssh_keys,
)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

_SAMPLE_PRIVATE_KEY = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZWQy\n"
    "NTUxOQAAACBtest_fake_key_data_for_testing_onlyAAAAIHRlc3RfdGVzdF90ZXN0X3Rl\n"
    "c3RfdGVzdF90ZXN0dGVzdAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n"
    "AAAAAAAAAAAAB3NzaC1lZDI1NTE5AAAAIHRlc3RfdGVzdF90ZXN0X3Rlc3RfdGVzdF90ZXN0\n"
    "dGVzdAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n"
    "-----END OPENSSH PRIVATE KEY-----\n"
)
_SAMPLE_PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHRlc3RfdGVzdA== test@test"


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


async def test_import_and_list(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool)
    svc = _mock_vault_svc()

    with patch("rag.services.ssh_keys.HarpocrateVaultClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        async with pool.acquire() as conn:
            created = await import_ssh_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=SshKeyImport(
                    key_id="deploy-test",
                    name="Deploy test",
                    private_key=_SAMPLE_PRIVATE_KEY,
                    public_key=_SAMPLE_PUBLIC_KEY,
                ),
            )

    assert created.key_id == "deploy-test"
    assert created.name == "Deploy test"
    assert created.public_key == _SAMPLE_PUBLIC_KEY
    assert created.passphrase_protected is False
    assert created.harpo_path == "${vault://v1:/ssh/deploy-test/private_key}"
    mock_client.set_secret.assert_called_once_with(
        "/ssh/deploy-test/private_key", _SAMPLE_PRIVATE_KEY
    )

    async with pool.acquire() as conn:
        keys = await list_ssh_keys(conn, vault_id=vault["id"])
    assert len(keys) == 1
    assert keys[0].key_id == "deploy-test"


async def test_import_with_passphrase(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v2")
    svc = _mock_vault_svc()

    with patch("rag.services.ssh_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await import_ssh_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=SshKeyImport(
                    key_id="enc-key",
                    name="Encrypted",
                    private_key=_SAMPLE_PRIVATE_KEY,
                    public_key=_SAMPLE_PUBLIC_KEY,
                    passphrase="secret123",
                ),
            )

    assert created.passphrase_protected is True


async def test_generate_ed25519(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v3")
    svc = _mock_vault_svc()

    with patch("rag.services.ssh_keys.HarpocrateVaultClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        async with pool.acquire() as conn:
            created = await generate_ssh_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=SshKeyGenerate(key_id="gen-ed25519", name="Generated Ed25519", key_type="ed25519"),
            )

    assert created.key_type == "ed25519"
    assert created.public_key.startswith("ssh-ed25519 ")
    assert "-----BEGIN OPENSSH PRIVATE KEY-----" not in created.public_key
    mock_client.set_secret.assert_called_once()
    _, private_pem = mock_client.set_secret.call_args[0]
    assert "BEGIN OPENSSH PRIVATE KEY" in private_pem


async def test_generate_rsa4096(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v4")
    svc = _mock_vault_svc()

    with patch("rag.services.ssh_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await generate_ssh_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=SshKeyGenerate(key_id="gen-rsa", name="Generated RSA", key_type="rsa-4096"),
            )

    assert created.key_type == "rsa-4096"
    assert created.public_key.startswith("ssh-rsa ")


async def test_generate_ecdsa256(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v5")
    svc = _mock_vault_svc()

    with patch("rag.services.ssh_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await generate_ssh_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=SshKeyGenerate(key_id="gen-ecdsa", name="Generated ECDSA", key_type="ecdsa-256"),
            )

    assert created.key_type == "ecdsa-256"
    assert created.public_key.startswith("ecdsa-sha2-nistp256 ")


async def test_duplicate_key_id_raises(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v6")
    svc = _mock_vault_svc()

    with patch("rag.services.ssh_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            await import_ssh_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=SshKeyImport(
                    key_id="dup",
                    name="First",
                    private_key=_SAMPLE_PRIVATE_KEY,
                    public_key=_SAMPLE_PUBLIC_KEY,
                ),
            )

    with patch("rag.services.ssh_keys.HarpocrateVaultClient"):
        with pytest.raises(DuplicateSshKeyError):
            async with pool.acquire() as conn:
                await import_ssh_key(
                    conn,
                    vault=vault,
                    vault_svc=svc,
                    req=SshKeyImport(
                        key_id="dup",
                        name="Second",
                        private_key=_SAMPLE_PRIVATE_KEY,
                        public_key=_SAMPLE_PUBLIC_KEY,
                    ),
                )


async def test_delete_ssh_key(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v7")
    svc = _mock_vault_svc()

    with patch("rag.services.ssh_keys.HarpocrateVaultClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        async with pool.acquire() as conn:
            created = await import_ssh_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=SshKeyImport(
                    key_id="del-me",
                    name="To delete",
                    private_key=_SAMPLE_PRIVATE_KEY,
                    public_key=_SAMPLE_PUBLIC_KEY,
                ),
            )

    with patch("rag.services.ssh_keys.HarpocrateVaultClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        async with pool.acquire() as conn:
            deleted = await delete_ssh_key(
                conn,
                key_id=str(created.id),
                vault=vault,
                vault_svc=svc,
            )

    assert deleted is True
    mock_client.delete_secret.assert_called_once()

    async with pool.acquire() as conn:
        keys = await list_ssh_keys(conn, vault_id=vault["id"])
    assert keys == []
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/integration/test_services_ssh_keys.py --collect-only 2>&1 | head -10
```

Résultat attendu : `ImportError` (module inexistant).

- [ ] **Créer `backend/src/rag/services/ssh_keys.py`**

```python
from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import asyncpg
import structlog
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa

from rag.schemas.ssh_keys import SshKeyGenerate, SshKeyImport, SshKeyOut
from rag.secrets.refs import build_ref, parse_ref
from rag.secrets.vault import HarpocrateVaultClient

log = structlog.get_logger(__name__)


class DuplicateSshKeyError(Exception):
    pass


class SshKeyNotFoundError(Exception):
    pass


def _build_secret_path(key_id: str) -> str:
    return f"/ssh/{key_id}/private_key"


def _build_vault_ref(vault_name: str, key_id: str) -> str:
    return build_ref(vault_name, _build_secret_path(key_id))


async def _get_vault_client(
    conn: asyncpg.Connection,
    vault: dict[str, Any],
    vault_svc: Any,
) -> HarpocrateVaultClient:
    api_key = await vault_svc.reveal_api_key(conn, UUID(vault["id"]))
    if api_key is None:
        raise RuntimeError("Cannot decrypt vault API key — DEK manquant ?")
    return HarpocrateVaultClient(url=vault["base_url"], token=api_key)


def _generate_key_pair(key_type: str) -> tuple[str, str]:
    """Retourne (private_pem, public_openssh)."""
    if key_type == "ed25519":
        private = ed25519.Ed25519PrivateKey.generate()
    elif key_type == "rsa-4096":
        private = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    elif key_type == "ecdsa-256":
        private = ec.generate_private_key(ec.SECP256R1())
    else:
        raise ValueError(f"Unsupported key_type: {key_type!r}")

    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    public_ssh = private.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode()

    return private_pem, public_ssh


async def list_ssh_keys(
    conn: asyncpg.Connection,
    *,
    vault_id: str,
) -> list[SshKeyOut]:
    rows = await conn.fetch(
        "SELECT id, key_id, name, key_type, public_key, passphrase_protected, "
        "harpo_path, created_at "
        "FROM ssh_keys WHERE vault_id = $1::uuid ORDER BY key_id",
        vault_id,
    )
    return [SshKeyOut.model_validate(dict(r)) for r in rows]


async def import_ssh_key(
    conn: asyncpg.Connection,
    *,
    vault: dict[str, Any],
    vault_svc: Any,
    req: SshKeyImport,
) -> SshKeyOut:
    secret_path = _build_secret_path(req.key_id)
    vault_ref = _build_vault_ref(vault["name"], req.key_id)
    passphrase_protected = req.passphrase is not None and len(req.passphrase) > 0

    client = await _get_vault_client(conn, vault, vault_svc)
    await asyncio.to_thread(client.set_secret, secret_path, req.private_key)

    try:
        row = await conn.fetchrow(
            "INSERT INTO ssh_keys "
            "(key_id, name, key_type, public_key, passphrase_protected, vault_id, harpo_path) "
            "VALUES ($1, $2, 'imported', $3, $4, $5::uuid, $6) "
            "RETURNING id, key_id, name, key_type, public_key, passphrase_protected, "
            "harpo_path, created_at",
            req.key_id,
            req.name,
            req.public_key,
            passphrase_protected,
            vault["id"],
            vault_ref,
        )
    except asyncpg.UniqueViolationError as exc:
        await asyncio.to_thread(client.delete_secret, secret_path)
        raise DuplicateSshKeyError(
            f"key_id={req.key_id!r} already exists in this vault"
        ) from exc

    log.info("ssh_key.imported", vault_id=vault["id"], key_id=req.key_id)
    return SshKeyOut.model_validate(dict(row))


async def generate_ssh_key(
    conn: asyncpg.Connection,
    *,
    vault: dict[str, Any],
    vault_svc: Any,
    req: SshKeyGenerate,
) -> SshKeyOut:
    secret_path = _build_secret_path(req.key_id)
    vault_ref = _build_vault_ref(vault["name"], req.key_id)

    private_pem, public_ssh = await asyncio.to_thread(_generate_key_pair, req.key_type)

    client = await _get_vault_client(conn, vault, vault_svc)
    await asyncio.to_thread(client.set_secret, secret_path, private_pem)

    try:
        row = await conn.fetchrow(
            "INSERT INTO ssh_keys "
            "(key_id, name, key_type, public_key, passphrase_protected, vault_id, harpo_path) "
            "VALUES ($1, $2, $3, $4, false, $5::uuid, $6) "
            "RETURNING id, key_id, name, key_type, public_key, passphrase_protected, "
            "harpo_path, created_at",
            req.key_id,
            req.name,
            req.key_type,
            public_ssh,
            vault["id"],
            vault_ref,
        )
    except asyncpg.UniqueViolationError as exc:
        await asyncio.to_thread(client.delete_secret, secret_path)
        raise DuplicateSshKeyError(
            f"key_id={req.key_id!r} already exists in this vault"
        ) from exc

    log.info("ssh_key.generated", vault_id=vault["id"], key_id=req.key_id, key_type=req.key_type)
    return SshKeyOut.model_validate(dict(row))


async def delete_ssh_key(
    conn: asyncpg.Connection,
    *,
    key_id: str,
    vault: dict[str, Any],
    vault_svc: Any,
) -> bool:
    row = await conn.fetchrow(
        "SELECT id, harpo_path FROM ssh_keys "
        "WHERE id = $1::uuid AND vault_id = $2::uuid",
        key_id,
        vault["id"],
    )
    if row is None:
        return False

    _, secret_path = parse_ref(row["harpo_path"])
    client = await _get_vault_client(conn, vault, vault_svc)
    await asyncio.to_thread(client.delete_secret, secret_path)

    await conn.execute("DELETE FROM ssh_keys WHERE id = $1::uuid", key_id)
    log.info("ssh_key.deleted", id=key_id, harpo_path=row["harpo_path"])
    return True
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/services/ssh_keys.py
```

Résultat attendu : aucune erreur.

- [ ] **Commit**

```bash
git add backend/src/rag/services/ssh_keys.py \
        backend/tests/integration/test_services_ssh_keys.py
git commit -m "feat(services): SSH keys — import + génération Ed25519/RSA-4096/ECDSA-256"
```

---

## Task 4 : Router API + enregistrement

**Files:**
- Create: `backend/src/rag/api/admin_ssh_keys.py`
- Modify: `backend/src/rag/main.py`

- [ ] **Créer `backend/src/rag/api/admin_ssh_keys.py`**

```python
from __future__ import annotations

from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.schemas.ssh_keys import SshKeyGenerate, SshKeyImport, SshKeyOut
from rag.services.ssh_keys import (
    DuplicateSshKeyError,
    delete_ssh_key,
    generate_ssh_key,
    import_ssh_key,
    list_ssh_keys,
)

log = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/admin/harpocrate-vaults/{vault_id}/ssh-keys",
    tags=["admin-ssh-keys"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


def _pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pools.config_pool  # type: ignore[no-any-return]


def _vault_svc(request: Request) -> object:
    return request.app.state.harpocrate_vaults_service


@router.get("", response_model=list[SshKeyOut])
async def list_keys(vault_id: UUID, request: Request) -> list[SshKeyOut]:
    pool = _pool(request)
    async with pool.acquire() as conn:
        return await list_ssh_keys(conn, vault_id=str(vault_id))


@router.post("/import", response_model=SshKeyOut, status_code=201)
async def import_key(
    vault_id: UUID,
    body: SshKeyImport,
    request: Request,
) -> SshKeyOut:
    pool = _pool(request)
    svc = _vault_svc(request)
    async with pool.acquire() as conn:
        vault = await svc.get_by_id(conn, vault_id)
        if vault is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
        vault_dict = {"id": str(vault.id), "name": vault.name, "base_url": vault.base_url}
        try:
            return await import_ssh_key(conn, vault=vault_dict, vault_svc=svc, req=body)
        except DuplicateSshKeyError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/generate", response_model=SshKeyOut, status_code=201)
async def generate_key(
    vault_id: UUID,
    body: SshKeyGenerate,
    request: Request,
) -> SshKeyOut:
    pool = _pool(request)
    svc = _vault_svc(request)
    async with pool.acquire() as conn:
        vault = await svc.get_by_id(conn, vault_id)
        if vault is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
        vault_dict = {"id": str(vault.id), "name": vault.name, "base_url": vault.base_url}
        try:
            return await generate_ssh_key(conn, vault=vault_dict, vault_svc=svc, req=body)
        except DuplicateSshKeyError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


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
        deleted = await delete_ssh_key(
            conn, key_id=str(key_id), vault=vault_dict, vault_svc=svc
        )
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ssh key not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Enregistrer dans `backend/src/rag/main.py`**

Après `from rag.api.admin_git_credentials import router as admin_git_credentials_router` :

```python
from rag.api.admin_ssh_keys import router as admin_ssh_keys_router
```

Après `app.include_router(admin_git_credentials_router)` :

```python
app.include_router(admin_ssh_keys_router)
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/api/admin_ssh_keys.py src/rag/main.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/api/admin_ssh_keys.py backend/src/rag/main.py
git commit -m "feat(api): router SSH keys (import + generate + delete)"
```

---

## Task 5 : Frontend — types + API client + hooks + i18n

**Files:**
- Modify: `frontend/src/lib/harpocrate-vaults.types.ts`
- Modify: `frontend/src/lib/harpocrate-vaults.ts`
- Modify: `frontend/src/hooks/useHarpocrateVaults.ts`
- Modify: `frontend/src/i18n/fr/harpocrate.json`
- Modify: `frontend/src/i18n/en/harpocrate.json`

- [ ] **Ajouter les types dans `harpocrate-vaults.types.ts`**

Ajouter à la fin du fichier :

```typescript
export type SshKeyType = "ed25519" | "rsa-4096" | "ecdsa-256";

export type SshKey = {
  id: string;
  key_id: string;
  name: string;
  key_type: string;
  public_key: string;
  passphrase_protected: boolean;
  harpo_path: string;
  created_at: string;
};

export type SshKeyImport = {
  key_id: string;
  name: string;
  private_key: string;
  public_key: string;
  passphrase?: string | null;
};

export type SshKeyGenerate = {
  key_id: string;
  name: string;
  key_type: SshKeyType;
};
```

- [ ] **Ajouter les fonctions API dans `harpocrate-vaults.ts`**

Ajouter les imports :

```typescript
import type {
  // ...existants...
  SshKey,
  SshKeyGenerate,
  SshKeyImport,
} from "@/lib/harpocrate-vaults.types";
```

Ajouter dans `harpocrateVaultsApi` après `deleteGitCredential` :

```typescript
  listSshKeys: (vaultId: string) =>
    api.get<SshKey[]>(`${BASE}/${vaultId}/ssh-keys`),

  importSshKey: (vaultId: string, payload: SshKeyImport) =>
    api.post<SshKey>(`${BASE}/${vaultId}/ssh-keys/import`, payload),

  generateSshKey: (vaultId: string, payload: SshKeyGenerate) =>
    api.post<SshKey>(`${BASE}/${vaultId}/ssh-keys/generate`, payload),

  deleteSshKey: (vaultId: string, keyId: string) =>
    api.delete<void>(`${BASE}/${vaultId}/ssh-keys/${keyId}`),
```

- [ ] **Ajouter les hooks dans `useHarpocrateVaults.ts`**

Ajouter les imports de types :

```typescript
import type {
  // ...existants...
  SshKeyGenerate,
  SshKeyImport,
} from "@/lib/harpocrate-vaults.types";
```

Ajouter à la fin du fichier :

```typescript
export function useSshKeys(vaultId: string | null) {
  return useQuery({
    queryKey: [...ROOT_KEY, vaultId, "ssh-keys"],
    queryFn: () => harpocrateVaultsApi.listSshKeys(vaultId as string),
    enabled: !!vaultId,
    staleTime: 30_000,
  });
}

export function useImportSshKey(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: SshKeyImport) =>
      harpocrateVaultsApi.importSshKey(vaultId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "ssh-keys"] });
    },
  });
}

export function useGenerateSshKey(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: SshKeyGenerate) =>
      harpocrateVaultsApi.generateSshKey(vaultId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "ssh-keys"] });
    },
  });
}

export function useDeleteSshKey(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) => harpocrateVaultsApi.deleteSshKey(vaultId, keyId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "ssh-keys"] });
    },
  });
}
```

- [ ] **Ajouter les clés i18n FR** dans `frontend/src/i18n/fr/harpocrate.json`

Ajouter dans l'objet racine après le bloc `"gitkeys"` :

```json
"ssh": {
  "tab": "SSH",
  "import_btn": "Importer une clé",
  "generate_btn": "Générer une clé",
  "empty": "Aucune clé SSH configurée pour ce coffre.",
  "col_key_id": "ID",
  "col_type": "Type",
  "col_name": "Nom",
  "col_public_key": "Clé publique",
  "delete_btn": "Supprimer",
  "delete_confirm_title": "Supprimer cette clé SSH ?",
  "delete_confirm_body": "La clé privée sera supprimée dans Harpocrate. Action irréversible.",
  "deleted_toast": "Clé SSH supprimée.",
  "error_toast": "Une erreur est survenue.",
  "error_duplicate": "Un ID identique existe déjà pour ce coffre.",
  "import_dialog_title": "Importer une clé SSH",
  "import_dialog_subtitle": "Importez un fichier de clé privée existant (.pem, .key, id_rsa, id_ed25519).",
  "field_name": "Nom",
  "field_key_id": "ID (slug)",
  "field_key_id_help": "Lettres, chiffres, - et _ uniquement",
  "field_private_key": "Clé privée",
  "field_public_key": "Clé publique",
  "field_passphrase": "Passphrase",
  "field_passphrase_placeholder": "Optionnel",
  "choose_file": "Choisir un fichier",
  "path_preview": "Path Harpocrate :",
  "import_btn_submit": "Importer",
  "generate_dialog_title": "Générer une paire de clés SSH",
  "field_key_type": "Type de clé",
  "generate_btn_submit": "Générer",
  "generated_public_key_title": "Clé publique générée",
  "generated_public_key_help": "Collez cette clé dans les paramètres SSH de GitHub / GitLab.",
  "copy_public_key": "Copier la clé publique",
  "copied_toast": "Clé publique copiée.",
  "cancel": "Annuler",
  "close": "Fermer"
}
```

- [ ] **Ajouter les clés i18n EN** dans `frontend/src/i18n/en/harpocrate.json`

```json
"ssh": {
  "tab": "SSH",
  "import_btn": "Import key",
  "generate_btn": "Generate key",
  "empty": "No SSH keys configured for this vault.",
  "col_key_id": "ID",
  "col_type": "Type",
  "col_name": "Name",
  "col_public_key": "Public key",
  "delete_btn": "Delete",
  "delete_confirm_title": "Delete this SSH key?",
  "delete_confirm_body": "The private key will be deleted from Harpocrate. This action is irreversible.",
  "deleted_toast": "SSH key deleted.",
  "error_toast": "An error occurred.",
  "error_duplicate": "An identical ID already exists for this vault.",
  "import_dialog_title": "Import SSH key",
  "import_dialog_subtitle": "Import an existing private key file (.pem, .key, id_rsa, id_ed25519).",
  "field_name": "Name",
  "field_key_id": "ID (slug)",
  "field_key_id_help": "Letters, digits, - and _ only",
  "field_private_key": "Private key",
  "field_public_key": "Public key",
  "field_passphrase": "Passphrase",
  "field_passphrase_placeholder": "Optional",
  "choose_file": "Choose file",
  "path_preview": "Harpocrate path:",
  "import_btn_submit": "Import",
  "generate_dialog_title": "Generate SSH key pair",
  "field_key_type": "Key type",
  "generate_btn_submit": "Generate",
  "generated_public_key_title": "Generated public key",
  "generated_public_key_help": "Paste this key in the SSH settings of GitHub / GitLab.",
  "copy_public_key": "Copy public key",
  "copied_toast": "Public key copied.",
  "cancel": "Cancel",
  "close": "Close"
}
```

- [ ] **Vérifier TypeScript + JSON**

```bash
cd frontend && npx tsc --noEmit
node -e "JSON.parse(require('fs').readFileSync('src/i18n/fr/harpocrate.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/en/harpocrate.json','utf8')); console.log('JSON OK')"
```

- [ ] **Commit**

```bash
git add frontend/src/lib/harpocrate-vaults.types.ts \
        frontend/src/lib/harpocrate-vaults.ts \
        frontend/src/hooks/useHarpocrateVaults.ts \
        frontend/src/i18n/fr/harpocrate.json \
        frontend/src/i18n/en/harpocrate.json
git commit -m "feat(front): types + API client + hooks + i18n SSH keys"
```

---

## Task 6 : ImportSshKeyDialog

**Files:**
- Create: `frontend/src/pages/harpocrate/ImportSshKeyDialog.tsx`

- [ ] **Créer `frontend/src/pages/harpocrate/ImportSshKeyDialog.tsx`**

```tsx
import { useRef, useState, type ChangeEvent, type FormEvent } from "react";
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
import { Textarea } from "@/components/ui/textarea";
import { useImportSshKey } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";

const KEY_ID_RE = /^[a-zA-Z0-9_-]+$/;

interface Props {
  vaultId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ImportSshKeyDialog({ vaultId, open, onOpenChange }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const mutation = useImportSshKey(vaultId);

  const [name, setName] = useState("");
  const [keyId, setKeyId] = useState("");
  const [privateKey, setPrivateKey] = useState("");
  const [publicKey, setPublicKey] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [keyIdError, setKeyIdError] = useState("");

  const privateFileRef = useRef<HTMLInputElement>(null);
  const publicFileRef = useRef<HTMLInputElement>(null);

  const harpoPath = keyId ? `/ssh/${keyId}/private_key` : "";

  function validateKeyId(v: string) {
    setKeyIdError(v && !KEY_ID_RE.test(v) ? t("ssh.field_key_id_help") : "");
  }

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setName(""); setKeyId(""); setPrivateKey("");
      setPublicKey(""); setPassphrase(""); setKeyIdError("");
    }
  }

  function readFile(
    e: ChangeEvent<HTMLInputElement>,
    setter: (v: string) => void,
  ) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => setter((ev.target?.result as string) ?? "");
    reader.readAsText(file);
  }

  const canSubmit =
    name.trim().length > 0 &&
    keyId.length > 0 &&
    KEY_ID_RE.test(keyId) &&
    privateKey.trim().length > 0 &&
    publicKey.trim().length > 0 &&
    !mutation.isPending;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    try {
      await mutation.mutateAsync({
        key_id: keyId,
        name,
        private_key: privateKey,
        public_key: publicKey,
        passphrase: passphrase || null,
      });
      toast({ title: t("ssh.import_btn_submit") + " OK" });
      handleClose(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("ssh.error_duplicate"), variant: "destructive" });
      } else {
        toast({ title: t("ssh.error_toast"), variant: "destructive" });
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[540px]">
        <DialogHeader>
          <DialogTitle>{t("ssh.import_dialog_title")}</DialogTitle>
          <DialogDescription>{t("ssh.import_dialog_subtitle")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("ssh.field_name")}
            </Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Déploiement production"
              className="mt-1"
            />
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("ssh.field_key_id")}
            </Label>
            <Input
              value={keyId}
              onChange={(e) => { setKeyId(e.target.value); validateKeyId(e.target.value); }}
              placeholder="deploy-prod"
              className="mt-1 font-mono"
            />
            {keyIdError ? (
              <p className="mt-1 text-xs text-rose-600">{keyIdError}</p>
            ) : (
              <p className="mt-1 text-xs text-slate-400">{t("ssh.field_key_id_help")}</p>
            )}
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("ssh.field_private_key")}
            </Label>
            <div className="mt-1 flex flex-col gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-fit"
                onClick={() => privateFileRef.current?.click()}
              >
                {t("ssh.choose_file")}
              </Button>
              <input
                ref={privateFileRef}
                type="file"
                accept=".pem,.key,id_rsa,id_ed25519,id_ecdsa"
                className="hidden"
                onChange={(e) => readFile(e, setPrivateKey)}
              />
              <Textarea
                value={privateKey}
                onChange={(e) => setPrivateKey(e.target.value)}
                placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
                className="font-mono text-xs min-h-[80px]"
              />
            </div>
            {harpoPath && (
              <p className="mt-1 text-xs text-slate-400">
                <span className="font-medium">{t("ssh.path_preview")}</span>{" "}
                <code className="font-mono">{harpoPath}</code>
              </p>
            )}
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("ssh.field_public_key")}
            </Label>
            <div className="mt-1 flex flex-col gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-fit"
                onClick={() => publicFileRef.current?.click()}
              >
                {t("ssh.choose_file")}
              </Button>
              <input
                ref={publicFileRef}
                type="file"
                accept=".pub"
                className="hidden"
                onChange={(e) => readFile(e, setPublicKey)}
              />
              <Textarea
                value={publicKey}
                onChange={(e) => setPublicKey(e.target.value)}
                placeholder="ssh-ed25519 AAAA... or ssh-rsa AAAA..."
                className="font-mono text-xs min-h-[60px]"
              />
            </div>
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("ssh.field_passphrase")}
            </Label>
            <Input
              type="password"
              value={passphrase}
              onChange={(e) => setPassphrase(e.target.value)}
              placeholder={t("ssh.field_passphrase_placeholder")}
              className="mt-1"
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              {t("ssh.cancel")}
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {t("ssh.import_btn_submit")}
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

- [ ] **Commit**

```bash
git add frontend/src/pages/harpocrate/ImportSshKeyDialog.tsx
git commit -m "feat(front): ImportSshKeyDialog"
```

---

## Task 7 : GenerateSshKeyDialog

**Files:**
- Create: `frontend/src/pages/harpocrate/GenerateSshKeyDialog.tsx`

- [ ] **Créer `frontend/src/pages/harpocrate/GenerateSshKeyDialog.tsx`**

```tsx
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Check } from "lucide-react";
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
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useGenerateSshKey } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";
import type { SshKeyType } from "@/lib/harpocrate-vaults.types";

const KEY_ID_RE = /^[a-zA-Z0-9_-]+$/;

const KEY_TYPES: { value: SshKeyType; label: string }[] = [
  { value: "ed25519", label: "Ed25519 (recommandé)" },
  { value: "rsa-4096", label: "RSA-4096" },
  { value: "ecdsa-256", label: "ECDSA-256" },
];

interface Props {
  vaultId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function GenerateSshKeyDialog({ vaultId, open, onOpenChange }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const mutation = useGenerateSshKey(vaultId);

  const [name, setName] = useState("");
  const [keyId, setKeyId] = useState("");
  const [keyType, setKeyType] = useState<SshKeyType>("ed25519");
  const [keyIdError, setKeyIdError] = useState("");
  const [generatedPublicKey, setGeneratedPublicKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  function validateKeyId(v: string) {
    setKeyIdError(v && !KEY_ID_RE.test(v) ? t("ssh.field_key_id_help") : "");
  }

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setName(""); setKeyId(""); setKeyType("ed25519");
      setKeyIdError(""); setGeneratedPublicKey(null); setCopied(false);
    }
  }

  async function handleCopy() {
    if (!generatedPublicKey) return;
    await navigator.clipboard.writeText(generatedPublicKey);
    setCopied(true);
    toast({ title: t("ssh.copied_toast") });
    setTimeout(() => setCopied(false), 2000);
  }

  const canSubmit =
    name.trim().length > 0 &&
    keyId.length > 0 &&
    KEY_ID_RE.test(keyId) &&
    !mutation.isPending;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    try {
      const result = await mutation.mutateAsync({ key_id: keyId, name, key_type: keyType });
      setGeneratedPublicKey(result.public_key);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("ssh.error_duplicate"), variant: "destructive" });
      } else {
        toast({ title: t("ssh.error_toast"), variant: "destructive" });
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("ssh.generate_dialog_title")}</DialogTitle>
        </DialogHeader>

        {generatedPublicKey ? (
          <div className="space-y-4">
            <div>
              <p className="text-sm font-medium text-slate-700">
                {t("ssh.generated_public_key_title")}
              </p>
              <p className="mt-1 text-xs text-slate-500">{t("ssh.generated_public_key_help")}</p>
              <Textarea
                value={generatedPublicKey}
                readOnly
                className="mt-2 font-mono text-xs min-h-[80px] bg-slate-50"
              />
            </div>
            <DialogFooter>
              <Button type="button" onClick={handleCopy} className="gap-2">
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                {t("ssh.copy_public_key")}
              </Button>
              <Button type="button" variant="outline" onClick={() => handleClose(false)}>
                {t("ssh.close")}
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("ssh.field_name")}
              </Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Déploiement production"
                className="mt-1"
              />
            </div>

            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("ssh.field_key_id")}
              </Label>
              <Input
                value={keyId}
                onChange={(e) => { setKeyId(e.target.value); validateKeyId(e.target.value); }}
                placeholder="deploy-prod"
                className="mt-1 font-mono"
              />
              {keyIdError ? (
                <p className="mt-1 text-xs text-rose-600">{keyIdError}</p>
              ) : (
                <p className="mt-1 text-xs text-slate-400">{t("ssh.field_key_id_help")}</p>
              )}
            </div>

            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("ssh.field_key_type")}
              </Label>
              <Select value={keyType} onValueChange={(v) => setKeyType(v as SshKeyType)}>
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {KEY_TYPES.map((k) => (
                    <SelectItem key={k.value} value={k.value}>
                      {k.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => handleClose(false)}>
                {t("ssh.cancel")}
              </Button>
              <Button type="submit" disabled={!canSubmit}>
                {mutation.isPending ? "…" : t("ssh.generate_btn_submit")}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Vérifier TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Commit**

```bash
git add frontend/src/pages/harpocrate/GenerateSshKeyDialog.tsx
git commit -m "feat(front): GenerateSshKeyDialog"
```

---

## Task 8 : VaultSshTab + VaultDetailPanel

**Files:**
- Create: `frontend/src/pages/harpocrate/VaultSshTab.tsx`
- Modify: `frontend/src/pages/harpocrate/VaultDetailPanel.tsx`

- [ ] **Créer `frontend/src/pages/harpocrate/VaultSshTab.tsx`**

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2, Copy, Check } from "lucide-react";
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
import { useDeleteSshKey, useSshKeys } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";
import type { SshKey } from "@/lib/harpocrate-vaults.types";
import { ImportSshKeyDialog } from "./ImportSshKeyDialog";
import { GenerateSshKeyDialog } from "./GenerateSshKeyDialog";

interface Props {
  vaultId: string;
}

export function VaultSshTab({ vaultId }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();

  const { data: keys = [], isLoading } = useSshKeys(vaultId);
  const deleteMutation = useDeleteSshKey(vaultId);

  const [importOpen, setImportOpen] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [toDelete, setToDelete] = useState<SshKey | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  async function handleCopy(key: SshKey) {
    await navigator.clipboard.writeText(key.public_key);
    setCopiedId(key.id);
    toast({ title: t("ssh.copied_toast") });
    setTimeout(() => setCopiedId(null), 2000);
  }

  async function handleDelete() {
    if (!toDelete) return;
    try {
      await deleteMutation.mutateAsync(toDelete.id);
      toast({ title: t("ssh.deleted_toast") });
    } catch {
      toast({ title: t("ssh.error_toast"), variant: "destructive" });
    } finally {
      setToDelete(null);
    }
  }

  return (
    <div className="space-y-4 pt-4">
      <div className="flex items-center justify-end gap-2">
        <Button size="sm" variant="outline" onClick={() => setImportOpen(true)}>
          {t("ssh.import_btn")}
        </Button>
        <Button size="sm" onClick={() => setGenerateOpen(true)}>
          {t("ssh.generate_btn")}
        </Button>
      </div>

      {!isLoading && keys.length === 0 ? (
        <div className="rounded border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("ssh.empty")}
        </div>
      ) : (
        <div className="overflow-hidden rounded border border-slate-200">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("ssh.col_key_id")}</TableHead>
                <TableHead>{t("ssh.col_type")}</TableHead>
                <TableHead>{t("ssh.col_name")}</TableHead>
                <TableHead>{t("ssh.col_public_key")}</TableHead>
                <TableHead className="w-20" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.map((k) => (
                <TableRow key={k.id}>
                  <TableCell className="font-mono text-sm">{k.key_id}</TableCell>
                  <TableCell>
                    <span className="rounded bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-700">
                      {k.key_type}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm text-slate-600">{k.name}</TableCell>
                  <TableCell className="max-w-[200px]">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-mono text-xs text-slate-500">
                        {k.public_key.slice(0, 40)}…
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleCopy(k)}
                        aria-label={t("ssh.copy_public_key")}
                      >
                        {copiedId === k.id ? (
                          <Check className="h-3.5 w-3.5 text-green-600" />
                        ) : (
                          <Copy className="h-3.5 w-3.5" />
                        )}
                      </Button>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setToDelete(k)}
                      className="text-rose-600 hover:text-rose-700"
                      aria-label={t("ssh.delete_btn")}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <ImportSshKeyDialog
        vaultId={vaultId}
        open={importOpen}
        onOpenChange={setImportOpen}
      />

      <GenerateSshKeyDialog
        vaultId={vaultId}
        open={generateOpen}
        onOpenChange={setGenerateOpen}
      />

      <AlertDialog
        open={!!toDelete}
        onOpenChange={(o) => { if (!o) setToDelete(null); }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("ssh.delete_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>{t("ssh.delete_confirm_body")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("ssh.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-rose-600 hover:bg-rose-700"
            >
              {t("ssh.delete_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
```

- [ ] **Modifier `VaultDetailPanel.tsx`** — ajouter l'onglet SSH

Ajouter l'import :

```tsx
import { VaultSshTab } from "@/pages/harpocrate/VaultSshTab";
```

Après `<TabsTrigger value="apikeys">{t("tabs.apikeys")}</TabsTrigger>` :

```tsx
<TabsTrigger value="ssh">{t("tabs.ssh")}</TabsTrigger>
```

Ajouter dans le fichier i18n `tabs` la clé `"ssh"` — mais elle est dans `ssh.tab`, donc dans `VaultDetailPanel` on utilise :

```tsx
<TabsTrigger value="ssh">{t("ssh.tab")}</TabsTrigger>
```

Après `</TabsContent>` (fin onglet apikeys) :

```tsx
<TabsContent value="ssh">
  <VaultSshTab vaultId={vault.id} />
</TabsContent>
```

- [ ] **Vérifier TypeScript + lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

- [ ] **Commit**

```bash
git add frontend/src/pages/harpocrate/VaultSshTab.tsx \
        frontend/src/pages/harpocrate/VaultDetailPanel.tsx
git commit -m "feat(front): VaultSshTab + onglet SSH dans VaultDetailPanel"
```
