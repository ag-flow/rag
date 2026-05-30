# Vault Ownership — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter `owner_id TEXT NOT NULL` sur `harpocrate_vaults` et filtrer les coffres par propriétaire : le coffre par défaut est visible de tous, les autres seulement par leur créateur.

**Architecture:** `owner_id = sha256(email.lower())` calculé côté backend. Nouvelle dépendance FastAPI `get_current_owner_id(request)` qui résout l'email depuis le contexte d'auth (master key → bootstrap admin email, local session → idem, OIDC → decode JWT). Le service `list_for_owner` filtre `WHERE is_default OR owner_id = $1`. Le router enforce la règle sur chaque opération.

**Tech Stack:** Python 3.12 / asyncpg / FastAPI / hashlib / pytest-asyncio

---

## Structure des fichiers

### Backend (créer)
- `backend/migrations/029_vault_owner.sql`
- `backend/src/rag/auth/owner.py`
- `backend/tests/unit/test_owner_id.py`

### Backend (modifier)
- `backend/src/rag/config.py` — ajouter `rag_bootstrap_admin_email`
- `backend/src/rag/schemas/harpocrate_vaults.py` — ajouter `owner_id` à `VaultSummary`
- `backend/src/rag/services/harpocrate_vaults.py` — queries + `list_for_owner` + `create` avec owner_id
- `backend/src/rag/api/admin_harpocrate_vaults.py` — injecter owner_id, enforcer accès

---

## Task 1 : Migration + Settings

**Files:**
- Create: `backend/migrations/029_vault_owner.sql`
- Modify: `backend/src/rag/config.py`

- [ ] **Créer la migration**

```sql
-- backend/migrations/029_vault_owner.sql
-- Migration 029 — ownership des coffres Harpocrate

ALTER TABLE harpocrate_vaults ADD COLUMN owner_id TEXT NOT NULL DEFAULT '';
CREATE INDEX harpocrate_vaults_owner ON harpocrate_vaults (owner_id);
```

Note : `DEFAULT ''` pour la migration DDL uniquement (DB reset assumé — aucun vault existant).

- [ ] **Ajouter `rag_bootstrap_admin_email` dans `backend/src/rag/config.py`**

Après `rag_bootstrap_admin_username: str = "admin"` :

```python
rag_bootstrap_admin_email: str = "admin@rag.io"
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/config.py
```

- [ ] **Commit**

```bash
git add backend/migrations/029_vault_owner.sql backend/src/rag/config.py
git commit -m "feat(db+config): migration 029 owner_id + rag_bootstrap_admin_email"
```

---

## Task 2 : auth/owner.py (TDD)

**Files:**
- Create: `backend/src/rag/auth/owner.py`
- Create: `backend/tests/unit/test_owner_id.py`

- [ ] **Écrire les tests (rouge)**

```python
# backend/tests/unit/test_owner_id.py
from __future__ import annotations

import hashlib
from unittest.mock import MagicMock

import pytest

from rag.auth.owner import email_to_owner_id, get_current_owner_id


def test_email_to_owner_id_is_sha256_lower() -> None:
    expected = hashlib.sha256("admin@rag.io".encode()).hexdigest()
    assert email_to_owner_id("admin@rag.io") == expected


def test_email_to_owner_id_lowercases() -> None:
    assert email_to_owner_id("Admin@RAG.io") == email_to_owner_id("admin@rag.io")


def test_get_current_owner_id_master_key(monkeypatch) -> None:
    """Master key auth → bootstrap admin email."""
    monkeypatch.setenv("RAG_MASTER_KEY", "x" * 64)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/db")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("RAG_BOOTSTRAP_ADMIN_EMAIL", "boss@example.com")

    from rag.config import Settings
    settings = Settings()

    request = MagicMock()
    request.headers.get.return_value = "Bearer somekey"
    request.app.state.settings = settings

    result = get_current_owner_id(request)
    assert result == email_to_owner_id("boss@example.com")


def test_get_current_owner_id_local_session(monkeypatch) -> None:
    """Session locale → bootstrap admin email."""
    monkeypatch.setenv("RAG_MASTER_KEY", "x" * 64)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/db")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("RAG_BOOTSTRAP_ADMIN_EMAIL", "boss@example.com")

    from rag.config import Settings
    settings = Settings()

    request = MagicMock()
    request.headers.get.return_value = None
    request.session = {"_local_session": {"expires_at": 9999999999, "username": "admin"}}
    request.app.state.settings = settings

    result = get_current_owner_id(request)
    assert result == email_to_owner_id("boss@example.com")


def test_get_current_owner_id_oidc_session() -> None:
    """Session OIDC → email depuis payload JWT."""
    import base64
    import json

    # Construire un faux JWT avec email dans le payload
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    payload_data = {"sub": "user123", "email": "alice@example.com", "exp": 9999999999}
    payload = base64.urlsafe_b64encode(
        json.dumps(payload_data).encode()
    ).rstrip(b"=").decode()
    fake_jwt = f"{header}.{payload}.fakesignature"

    request = MagicMock()
    request.headers.get.return_value = None
    request.session = {"_oidc_session": {"id_token": fake_jwt}}

    result = get_current_owner_id(request)
    assert result == email_to_owner_id("alice@example.com")
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_owner_id.py -v 2>&1 | head -10
```

Résultat attendu : `ImportError` (module inexistant).

- [ ] **Créer `backend/src/rag/auth/owner.py`**

```python
from __future__ import annotations

import base64
import hashlib
import json

from fastapi import Request


def email_to_owner_id(email: str) -> str:
    """Retourne sha256(email.lower()) comme identifiant owner."""
    return hashlib.sha256(email.lower().encode()).hexdigest()


def _decode_jwt_payload(token: str) -> dict:
    """Décode le payload d'un JWT sans vérification de signature."""
    payload_b64 = token.split(".")[1]
    padding = -len(payload_b64) % 4
    if padding:
        payload_b64 += "=" * padding
    return json.loads(base64.urlsafe_b64decode(payload_b64))


def get_current_owner_id(request: Request) -> str:
    """Résout le owner_id de la requête courante.

    Priorité :
    1. Bearer token → master key → email bootstrap admin
    2. Session locale → email bootstrap admin
    3. Session OIDC → email depuis JWT payload
    """
    settings = request.app.state.settings

    auth_header = request.headers.get("Authorization")
    if auth_header:
        return email_to_owner_id(settings.rag_bootstrap_admin_email)

    local_session = request.session.get("_local_session")
    if local_session:
        return email_to_owner_id(settings.rag_bootstrap_admin_email)

    oidc_session = request.session.get("_oidc_session")
    if oidc_session:
        id_token = oidc_session.get("id_token", "")
        claims = _decode_jwt_payload(id_token)
        email = claims.get("email", "")
        return email_to_owner_id(email)

    return email_to_owner_id(settings.rag_bootstrap_admin_email)
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_owner_id.py -v
```

Résultat attendu : 4 tests PASS.

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/auth/owner.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/auth/owner.py backend/tests/unit/test_owner_id.py
git commit -m "feat(auth): owner_id — email_to_owner_id + get_current_owner_id"
```

---

## Task 3 : Service + Schema — owner_id dans les queries

**Files:**
- Modify: `backend/src/rag/schemas/harpocrate_vaults.py`
- Modify: `backend/src/rag/services/harpocrate_vaults.py`

### Étape 1 — Ajouter `owner_id` à `VaultSummary`

Dans `backend/src/rag/schemas/harpocrate_vaults.py`, ajouter dans `VaultSummary` :

```python
owner_id: str = ""
```

(Valeur par défaut vide pour rétrocompatibilité avec les tests existants qui ne renseignent pas le champ.)

### Étape 2 — Mettre à jour les requêtes SQL dans le service

Dans `backend/src/rag/services/harpocrate_vaults.py` :

**1. Mettre à jour toutes les constantes `_SELECT_*` pour inclure `owner_id`**

Remplacer :
```python
_SELECT_ALL = (
    "SELECT id, name, label, base_url, api_key_id, probe_path, "
    "is_default, created_at, updated_at "
    "FROM harpocrate_vaults ORDER BY created_at"
)
```
Par :
```python
_SELECT_ALL = (
    "SELECT id, name, label, base_url, api_key_id, probe_path, "
    "is_default, owner_id, created_at, updated_at "
    "FROM harpocrate_vaults ORDER BY created_at"
)
```

Faire de même pour `_SELECT_BY_ID`, `_SELECT_BY_NAME`, `_SELECT_BY_API_KEY_ID`, `_SELECT_DEFAULT` et leurs RETURNING.

**2. Mettre à jour `_INSERT_VAULT`**

```python
_INSERT_VAULT = (
    "INSERT INTO harpocrate_vaults "
    "(id, name, label, base_url, api_key_id, api_key_encrypted, "
    "probe_path, is_default, owner_id) "
    "VALUES ($1, $2, $3, $4, $5, pgp_sym_encrypt($6::text, $7::text), $8, $9, $10) "
    "RETURNING id, name, label, base_url, api_key_id, probe_path, "
    "is_default, owner_id, created_at, updated_at"
)
```

**3. Mettre à jour `_UPDATE_VAULT_FULL` et `_UPDATE_ROTATE_API_KEY` RETURNING**

Ajouter `owner_id` dans tous les RETURNING.

**4. Ajouter la méthode `list_for_owner`**

```python
async def list_for_owner(self, conn: Connection, owner_id: str) -> list[VaultSummary]:
    rows = await conn.fetch(
        "SELECT id, name, label, base_url, api_key_id, probe_path, "
        "is_default, owner_id, created_at, updated_at "
        "FROM harpocrate_vaults "
        "WHERE is_default = true OR owner_id = $1 "
        "ORDER BY created_at",
        owner_id,
    )
    return [VaultSummary.model_validate(dict(r)) for r in rows]
```

**5. Mettre à jour la signature de `create`**

```python
async def create(
    self,
    conn: Connection,
    req: VaultCreateRequest,
    owner_id: str = "",
) -> VaultSummary:
```

Et dans le corps, passer `owner_id` comme `$10` à l'INSERT.

Trouver la ligne qui exécute `_INSERT_VAULT` et ajouter `owner_id` comme dernier paramètre.

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/services/harpocrate_vaults.py src/rag/schemas/harpocrate_vaults.py
```

- [ ] **Vérifier que les tests existants passent toujours**

```bash
cd backend && uv run pytest tests/unit/schemas/test_harpocrate_vaults_dto.py -v --collect-only 2>&1 | tail -5
```

- [ ] **Commit**

```bash
git add backend/src/rag/schemas/harpocrate_vaults.py \
        backend/src/rag/services/harpocrate_vaults.py
git commit -m "feat(services): owner_id dans HarpocrateVaultsService — list_for_owner + create"
```

---

## Task 4 : Router — injection owner_id + access control

**Files:**
- Modify: `backend/src/rag/api/admin_harpocrate_vaults.py`

- [ ] **Modifier `backend/src/rag/api/admin_harpocrate_vaults.py`**

**1. Ajouter l'import**

```python
from rag.auth.owner import get_current_owner_id
```

**2. Remplacer `list_vaults`**

```python
@router.get("", response_model=list[VaultSummary])
async def list_vaults(request: Request) -> list[VaultSummary]:
    svc = request.app.state.harpocrate_vaults_service
    pool = request.app.state.pools.config_pool
    owner_id = get_current_owner_id(request)
    async with pool.acquire() as conn:
        return await svc.list_for_owner(conn, owner_id)
```

**3. Modifier `create_vault`**

Ajouter `owner_id = get_current_owner_id(request)` et le passer à `svc.create(conn, req, owner_id=owner_id)` :

```python
@router.post("", status_code=status.HTTP_201_CREATED, response_model=VaultSummary)
async def create_vault(req: VaultCreateRequest, request: Request) -> VaultSummary:
    svc = request.app.state.harpocrate_vaults_service
    pool = request.app.state.pools.config_pool
    actor = _actor(request)
    owner_id = get_current_owner_id(request)
    async with pool.acquire() as conn:
        try:
            async with conn.transaction():
                v = await svc.create(conn, req, owner_id=owner_id)
        except VaultNameAlreadyExistsError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
    log.info("vault.created.http", vault_id=str(v.id), actor=actor)
    return v
```

**4. Ajouter le helper `_check_vault_access`**

```python
def _check_vault_access(
    vault: VaultSummary,
    owner_id: str,
    *,
    write: bool = False,
) -> None:
    """Lève 403 si l'owner ne correspond pas.

    - Lecture (write=False) : autorisé pour is_default OU owner_id match.
    - Écriture (write=True) : owner_id match obligatoire.
    """
    if write:
        if vault.owner_id != owner_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "not vault owner")
    else:
        if not vault.is_default and vault.owner_id != owner_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "not vault owner")
```

**5. Modifier `get_vault`**

```python
@router.get("/{vault_id}", response_model=VaultSummary)
async def get_vault(vault_id: UUID, request: Request) -> VaultSummary:
    svc = request.app.state.harpocrate_vaults_service
    pool = request.app.state.pools.config_pool
    owner_id = get_current_owner_id(request)
    async with pool.acquire() as conn:
        v = await svc.get_by_id(conn, vault_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
    _check_vault_access(v, owner_id, write=False)
    return v
```

**6. Modifier `update_vault`, `delete_vault`, `rotate_api_key`, `set_default`, `reveal_api_key`, `get_vault_info`, `list_vault_types`, `list_vault_secrets`, `test_connection`**

Pour toutes les routes de modification (`update_vault`, `delete_vault`, `rotate_api_key`, `set_default`), appeler `_check_vault_access(target, owner_id, write=True)` après avoir récupéré le vault.

Pour les routes de lecture (`get_vault_info`, `list_vault_types`, `list_vault_secrets`, `test_connection`, `reveal_api_key`), appeler `_check_vault_access(v, owner_id, write=False)`.

Exemple pour `update_vault` :

```python
@router.patch("/{vault_id}", response_model=VaultSummary)
async def update_vault(vault_id: UUID, req: VaultUpdateRequest, request: Request) -> VaultSummary:
    svc = request.app.state.harpocrate_vaults_service
    pool = request.app.state.pools.config_pool
    actor = _actor(request)
    owner_id = get_current_owner_id(request)
    async with pool.acquire() as conn:
        existing = await svc.get_by_id(conn, vault_id)
        if existing is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
        _check_vault_access(existing, owner_id, write=True)
        v = await svc.update(conn, vault_id, req)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
    log.info("vault.updated.http", vault_id=str(v.id), actor=actor)
    return v
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/api/admin_harpocrate_vaults.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/api/admin_harpocrate_vaults.py
git commit -m "feat(api): vault ownership — list_for_owner + _check_vault_access"
```

---

## Task 5 : Tests d'intégration ownership

**Files:**
- Create: `backend/tests/integration/test_vault_ownership.py`

- [ ] **Créer les tests**

```python
# backend/tests/integration/test_vault_ownership.py
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.auth.owner import email_to_owner_id
from rag.db.migrations import run_migrations
from rag.schemas.harpocrate_vaults import VaultCreateRequest
from rag.services.harpocrate_vaults import HarpocrateVaultsService

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
_DEK = "passphrase-of-at-least-32-characters-long"


def _settings(monkeypatch, email: str = "admin@rag.io"):
    monkeypatch.setenv("RAG_MASTER_KEY", "x" * 64)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/db")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("HARPOCRATE_DEK", _DEK)
    monkeypatch.setenv("RAG_BOOTSTRAP_ADMIN_EMAIL", email)


def _req(name: str, is_default: bool = False) -> VaultCreateRequest:
    return VaultCreateRequest(
        name=name,
        label=name,
        base_url="https://h.io",
        api_key_id="k",
        api_key="secret",
        is_default=is_default,
    )


@pytest.fixture
async def pool(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
    return session_pool


async def test_create_sets_owner_id(pool: asyncpg.Pool, monkeypatch) -> None:
    _settings(monkeypatch, "alice@example.com")
    from rag.config import Settings
    svc = HarpocrateVaultsService(Settings())
    owner_id = email_to_owner_id("alice@example.com")

    async with pool.acquire() as conn:
        v = await svc.create(conn, _req("v-alice"), owner_id=owner_id)

    assert v.owner_id == owner_id


async def test_list_for_owner_shows_own_and_default(pool: asyncpg.Pool, monkeypatch) -> None:
    _settings(monkeypatch)
    from rag.config import Settings
    svc = HarpocrateVaultsService(Settings())

    owner_alice = email_to_owner_id("alice@example.com")
    owner_bob = email_to_owner_id("bob@example.com")

    async with pool.acquire() as conn:
        default = await svc.create(conn, _req("default-v", is_default=True), owner_id=owner_alice)
        await svc.create(conn, _req("alice-v"), owner_id=owner_alice)
        await svc.create(conn, _req("bob-v"), owner_id=owner_bob)

    # Alice voit ses 2 vaults + le default (qui est le sien aussi ici)
    async with pool.acquire() as conn:
        alice_vaults = await svc.list_for_owner(conn, owner_alice)
    assert {v.name for v in alice_vaults} == {"default-v", "alice-v"}

    # Bob voit son vault + le default
    async with pool.acquire() as conn:
        bob_vaults = await svc.list_for_owner(conn, owner_bob)
    assert {v.name for v in bob_vaults} == {"default-v", "bob-v"}


async def test_list_for_owner_default_visible_to_all(pool: asyncpg.Pool, monkeypatch) -> None:
    _settings(monkeypatch)
    from rag.config import Settings
    svc = HarpocrateVaultsService(Settings())

    owner_alice = email_to_owner_id("alice@example.com")
    owner_bob = email_to_owner_id("bob@example.com")
    owner_carol = email_to_owner_id("carol@example.com")

    async with pool.acquire() as conn:
        await svc.create(conn, _req("shared-default", is_default=True), owner_id=owner_alice)

    # Carol n'a aucun vault propre mais voit le default
    async with pool.acquire() as conn:
        carol_vaults = await svc.list_for_owner(conn, owner_carol)
    assert len(carol_vaults) == 1
    assert carol_vaults[0].name == "shared-default"

    # Bob idem
    async with pool.acquire() as conn:
        bob_vaults = await svc.list_for_owner(conn, owner_bob)
    assert len(bob_vaults) == 1
```

- [ ] **Vérifier la collecte**

```bash
cd backend && uv run pytest tests/integration/test_vault_ownership.py --collect-only 2>&1 | tail -5
```

Résultat attendu : 3 tests collectés.

- [ ] **Commit**

```bash
git add backend/tests/integration/test_vault_ownership.py
git commit -m "test(integration): vault ownership — list_for_owner + owner_id filter"
```
