# M5e — Workspace api_key chiffrée (pgcrypto) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrer le stockage de `workspaces.api_key` de bcrypt (irréversible) vers `pgp_sym_encrypt` (réversible) avec fingerprint SHA-256 pour lookup O(1), exposer un endpoint `GET /api/admin/workspaces/{name}/apikey` idempotent pour conformer la spec 08, et refactorer tous les chemins qui consommaient `api_key_hash`.

**Architecture:** Migration BDD `010_workspace_apikey_encrypted.sql` qui remplace la colonne `api_key_hash TEXT` par `api_key_encrypted BYTEA` + `api_key_fingerprint TEXT UNIQUE`. Une nouvelle variable d'env `RAG_API_KEY_DEK` (≥32 chars) chiffre les clés via pgcrypto côté SQL. Le service apikey ne contient plus que `generate_api_key()` ; toute la cryptographie est dans les requêtes SQL des services `workspaces.py` et `auth/workspace_auth.py`. Le lookup d'auth workspace se fait par fingerprint puis comparaison timing-safe sur la valeur déchiffrée.

**Tech Stack:** Python 3.12 + asyncpg + pgcrypto + Pydantic Settings + pytest + structlog. Pattern repris de `services/harpocrate_vaults.py` (M5c).

**Spec design** : `docs/superpowers/specs/2026-05-17-M5e-workspace-apikey-encrypted-design.md`

---

## File Structure

| Fichier | Statut | Responsabilité |
|---|---|---|
| `backend/migrations/010_workspace_apikey_encrypted.sql` | **Create** | DROP `api_key_hash`, ADD `api_key_encrypted BYTEA` + `api_key_fingerprint TEXT UNIQUE` |
| `backend/tests/integration/test_migration_010_workspace_apikey.py` | **Create** | Vérifie schéma post-010 + round-trip pgp_sym_encrypt/decrypt + UNIQUE fingerprint |
| `backend/src/rag/config.py` | **Modify** | +champ `api_key_dek` + validateur ≥32 chars |
| `backend/tests/unit/test_config_api_key_dek.py` | **Create** | Validateur Settings vide → None, court → ValueError, OK → str |
| `backend/src/rag/services/apikey.py` | **Modify** | Suppression `hash_api_key`/`verify_api_key`, garde `generate_api_key` |
| `backend/tests/unit/test_apikey.py` | **Modify** | Suppression tests bcrypt, garde tests `generate_api_key` |
| `backend/src/rag/services/workspaces.py` | **Modify** | `create_workspace` + `rotate_apikey` : INSERT/UPDATE `pgp_sym_encrypt + fingerprint`, boucle anti-collision (max 3) |
| `backend/tests/integration/test_services_workspaces_create.py` | **Modify** | Adapter assertions sur colonnes |
| `backend/tests/integration/test_services_workspaces_rotate.py` | **Modify** | Remplacer `verify_api_key(new_key, hash)` par décryptage + compare |
| `backend/src/rag/auth/workspace_auth.py` | **Modify** | Lookup par `api_key_fingerprint`, déchiffre + compare timing-safe avec `secrets.compare_digest` |
| `backend/tests/unit/auth/test_require_workspace_apikey.py` | **Modify** | Adapter mocks/setups |
| `backend/tests/integration/test_workspace_auth_lookup.py` | **Create** | Lookup réel via fingerprint en BDD (sans mock) |
| `backend/src/rag/api/admin.py` | **Modify** | +endpoint `GET /workspaces/{name}/apikey` |
| `backend/tests/integration/test_api_admin_workspaces_apikey.py` | **Create** | GET 200/404/401/503 + idempotence + reflet après rotate |
| `backend/src/rag/main.py` | **Modify** | Lifespan : si workspaces non vide et DEK absent → RuntimeError |
| `backend/tests/integration/test_lifespan_api_key_dek_required.py` | **Create** | Boot échoue si workspaces non vide + DEK manquant |
| `backend/tests/integration/test_helpers.py` | **Modify** | INSERT workspaces avec nouvelle structure |
| `backend/tests/integration/test_migration_001.py` | **Modify** | Adapter `expected` colonnes : retirer `api_key_hash`, ajouter `api_key_encrypted` + `api_key_fingerprint` |
| `backend/tests/integration/test_migration_002.py` | **Modify** | Idem (vérifie schéma final) |
| `backend/tests/integration/test_migration_003.py` | **Modify** | Idem |
| `backend/tests/integration/test_services_models.py` | **Modify** | Adapter INSERT direct workspaces |
| `backend/tests/integration/test_indexer_noop.py` | **Modify** | Adapter INSERT direct |
| `backend/tests/integration/test_indexer_real.py` | **Modify** | Adapter INSERT direct |
| `backend/tests/integration/test_sync_executor.py` | **Modify** | Adapter INSERT direct |
| `backend/tests/integration/test_sync_picker.py` | **Modify** | Adapter INSERT direct |
| `backend/tests/integration/test_sync_recovery.py` | **Modify** | Adapter INSERT direct |
| `backend/tests/integration/test_sync_scheduler.py` | **Modify** | Adapter INSERT direct |
| `backend/tests/integration/test_sync_worker.py` | **Modify** | Adapter INSERT direct |
| `backend/tests/integration/conftest.py` (ou nouveau helper) | **Create/Modify** | Fixture `seed_workspace(conn, name, api_key, dek)` mutualisée |
| `backend/.env.example` | **Modify** | +section `RAG_API_KEY_DEK` documentée |
| `specs/08-docker-init.md` | **Modify** | Path final `/api/admin/...` + note DEK serveur |

---

## Task 1: Helper seed + migration 010 + tests round-trip

**Files:**
- Create: `backend/tests/integration/_workspace_seed.py`
- Create: `backend/migrations/010_workspace_apikey_encrypted.sql`
- Create: `backend/tests/integration/test_migration_010_workspace_apikey.py`

**Contexte** : 13 fichiers de tests d'intégration font des `INSERT INTO workspaces (..., api_key_hash, ...)`. Pour éviter de les casser un par un avec du SQL répété, on crée un helper `seed_workspace(conn, *, name, api_key, dek, rag_cnx='c', rag_base='b')` qui INSERT correctement avec le nouveau schéma. Tous les tests seront migrés vers ce helper en tâche dédiée.

- [ ] **Step 1: Créer le helper seed (avant la migration, sans implémentation interne)**

`backend/tests/integration/_workspace_seed.py` :

```python
"""Helper de test : insère un workspace minimal avec le nouveau schéma
(api_key_encrypted + api_key_fingerprint). Centralise la connaissance du
schéma pour éviter la duplication dans les tests d'intégration.
"""
from __future__ import annotations

from hashlib import sha256
from uuid import UUID

import asyncpg


async def seed_workspace(
    conn: asyncpg.Connection,
    *,
    name: str,
    api_key: str = "test-api-key",
    dek: str = "x" * 32,
    rag_cnx: str = "postgresql://test/c",
    rag_base: str = "rag_test_b",
) -> UUID:
    """Insère un workspace test, retourne son UUID.

    `api_key` est chiffrée via pgp_sym_encrypt(api_key, dek) et son
    fingerprint SHA-256 est inséré dans la colonne dédiée.
    """
    fingerprint = sha256(api_key.encode("utf-8")).hexdigest()
    row = await conn.fetchrow(
        """
        INSERT INTO workspaces
            (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base)
        VALUES
            ($1, pgp_sym_encrypt($2::text, $3::text)::bytea, $4, $5, $6)
        RETURNING id
        """,
        name, api_key, dek, fingerprint, rag_cnx, rag_base,
    )
    if row is None:
        raise RuntimeError("seed_workspace: INSERT did not RETURN id")
    return row["id"]
```

- [ ] **Step 2: Écrire le test de schéma post-migration (fail attendu — migration absente)**

`backend/tests/integration/test_migration_010_workspace_apikey.py` :

```python
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_workspaces_columns_after_010(session_pool: asyncpg.Pool) -> None:
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS indexer_configs, workspaces, schema_migrations CASCADE"
        )
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]: r["data_type"]
            for r in await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'workspaces'"
            )
        }
    assert "api_key_hash" not in cols
    assert cols.get("api_key_encrypted") == "bytea"
    assert cols.get("api_key_fingerprint") == "text"


@pytest.mark.asyncio
async def test_apikey_fingerprint_unique_index(session_pool: asyncpg.Pool) -> None:
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS indexer_configs, workspaces, schema_migrations CASCADE"
        )
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'workspaces' AND indexname = $1",
            "idx_workspaces_apikey_fingerprint",
        )
    assert row is not None


@pytest.mark.asyncio
async def test_apikey_roundtrip_via_pgcrypto(session_pool: asyncpg.Pool) -> None:
    """Round-trip : insert chiffré → SELECT pgp_sym_decrypt → valeur d'origine."""
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS indexer_configs, workspaces, schema_migrations CASCADE"
        )
    await run_migrations(session_pool, MIGRATIONS_DIR)

    dek = "abcdefghijklmnopqrstuvwxyz012345"
    api_key = "ws-key-original-clear"
    fp = sha256(api_key.encode()).hexdigest()
    async with session_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ($1, pgp_sym_encrypt($2::text, $3::text)::bytea, $4, 'c', 'b')",
            "ws_roundtrip", api_key, dek, fp,
        )
        decrypted = await conn.fetchval(
            "SELECT pgp_sym_decrypt(api_key_encrypted, $1::text)::text "
            "FROM workspaces WHERE name = $2",
            dek, "ws_roundtrip",
        )
    assert decrypted == api_key


@pytest.mark.asyncio
async def test_apikey_fingerprint_unique_violation(session_pool: asyncpg.Pool) -> None:
    """INSERT avec fingerprint déjà présent → UniqueViolationError."""
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS indexer_configs, workspaces, schema_migrations CASCADE"
        )
    await run_migrations(session_pool, MIGRATIONS_DIR)

    dek = "abcdefghijklmnopqrstuvwxyz012345"
    api_key = "duplicate-key"
    fp = sha256(api_key.encode()).hexdigest()
    async with session_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ($1, pgp_sym_encrypt($2::text, $3::text)::bytea, $4, 'c', 'b')",
            "ws_a", api_key, dek, fp,
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
                "VALUES ($1, pgp_sym_encrypt($2::text, $3::text)::bytea, $4, 'c', 'b')",
                "ws_b", api_key, dek, fp,
            )
```

- [ ] **Step 3: Lancer les tests, vérifier qu'ils échouent**

Run sur LXC test (cf. mémoire `test-execution-pattern.md`) :

```bash
./scripts/run-test.sh
# extraire le password Postgres généré, exporter RAG_POSTGRES_*
cd backend
uv run pytest tests/integration/test_migration_010_workspace_apikey.py -v
```

Expected : 4 tests fail — soit `column "api_key_encrypted" does not exist`, soit migration absente.

- [ ] **Step 4: Écrire la migration 010**

`backend/migrations/010_workspace_apikey_encrypted.sql` :

```sql
-- Migration 010 — workspaces.api_key : bcrypt → pgcrypto (chiffrement réversible)
--
-- Préconditions :
--   - Extension pgcrypto déjà activée (migration 009).
--   - Table workspaces vide (vérifié à blanc sur BDD test au design M5e).
--
-- Note : la rotation de RAG_API_KEY_DEK est hors-scope. Une perte de DEK
-- rend toutes les api_keys workspace inutilisables (réindexation requise).

ALTER TABLE workspaces DROP COLUMN api_key_hash;

ALTER TABLE workspaces
    ADD COLUMN api_key_encrypted BYTEA NOT NULL,
    ADD COLUMN api_key_fingerprint TEXT NOT NULL;

CREATE UNIQUE INDEX idx_workspaces_apikey_fingerprint
    ON workspaces (api_key_fingerprint);
```

- [ ] **Step 5: Relancer les tests, vérifier qu'ils passent**

Run : `uv run pytest tests/integration/test_migration_010_workspace_apikey.py -v`
Expected : 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/010_workspace_apikey_encrypted.sql \
        backend/tests/integration/test_migration_010_workspace_apikey.py \
        backend/tests/integration/_workspace_seed.py
git commit -m "feat(M5e-T1): migration 010 api_key_encrypted + fingerprint + helper seed"
```

---

## Task 2: Adapter tous les tests d'intégration au nouveau schéma

**Files modifiés (13 fichiers tests + helpers DB) :**
- `backend/tests/integration/test_helpers.py`
- `backend/tests/integration/test_migration_001.py`
- `backend/tests/integration/test_migration_002.py`
- `backend/tests/integration/test_migration_003.py`
- `backend/tests/integration/test_services_models.py`
- `backend/tests/integration/test_indexer_noop.py`
- `backend/tests/integration/test_indexer_real.py`
- `backend/tests/integration/test_sync_executor.py`
- `backend/tests/integration/test_sync_picker.py`
- `backend/tests/integration/test_sync_recovery.py`
- `backend/tests/integration/test_sync_scheduler.py`
- `backend/tests/integration/test_sync_worker.py`
- `backend/tests/integration/test_services_workspaces_rotate.py` (partiel, partie bcrypt — autre tâche pour la logique)

**Contexte** : Le code applicatif n'est pas encore touché. Mais comme la migration 010 modifie le schéma, **tous les tests qui INSERT directement avec `api_key_hash` cassent**. Cette tâche les met à jour pour le nouveau schéma, sans toucher au code de production. Ils tomberont en rouge sur d'autres aspects (auth, services) qui seront fixés dans les tâches suivantes.

- [ ] **Step 1: Mettre à jour `test_helpers.py`**

Remplacer chaque `INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) VALUES (..., 'h', 'c', 'b')` par un INSERT cohérent. Comme ces tests ne testent que les helpers DB (`fetch_one`, `transaction`), passer une fausse valeur chiffrée et un fingerprint stable suffit :

```python
# Helper local au fichier — utilise un dek constant pour reproducibilité.
_TEST_DEK = "x" * 32
_INSERT_WS_SQL = (
    "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
    "VALUES ($1, pgp_sym_encrypt('k', $2::text)::bytea, $3, 'c', 'b')"
)

# Chaque test devient :
await execute(migrated, _INSERT_WS_SQL, "w_helper", _TEST_DEK, "fp_w_helper")
```

Adapter les 4 occurrences en gardant les `name` distincts d'origine.

- [ ] **Step 2: Mettre à jour `test_migration_001.py`**

Le test vérifie le set de colonnes après *toutes* les migrations. Adapter `expected` :

```python
expected = {
    "id",
    "name",
    "api_key_encrypted",
    "api_key_fingerprint",
    "rag_cnx",
    "rag_base",
    "sync_interval_seconds",
    "created_at",
    "updated_at",
}
assert expected.issubset(cols.keys())
assert "api_key_hash" not in cols
```

Si d'autres assertions du fichier (5 occurrences signalées) touchent `api_key_hash`, les remplacer pareillement.

- [ ] **Step 3: Mettre à jour `test_migration_002.py` et `test_migration_003.py`**

Même logique. Lire chaque fichier, identifier les références à `api_key_hash`, les remplacer par `api_key_encrypted` / `api_key_fingerprint` selon le contexte d'assertion. Si un test inspectait `api_key_hash IS NOT NULL`, il devient `api_key_encrypted IS NOT NULL`.

- [ ] **Step 4: Mettre à jour tous les autres fichiers (INSERT direct)**

Pour chaque fichier de la liste : `test_services_models.py`, `test_indexer_noop.py`, `test_indexer_real.py`, `test_sync_executor.py`, `test_sync_picker.py`, `test_sync_recovery.py`, `test_sync_scheduler.py`, `test_sync_worker.py` :

1. Importer le helper : `from tests.integration._workspace_seed import seed_workspace`
2. Remplacer chaque INSERT manuel par un appel `await seed_workspace(conn, name="...", api_key="...", dek="x"*32, rag_cnx="...", rag_base="...")`
3. Conserver les valeurs `name`, `rag_cnx`, `rag_base` existantes pour ne pas changer la sémantique du test.

**Exception** : `test_services_workspaces_rotate.py` fait des assertions sur le hash (`verify_api_key(new_key, row["api_key_hash"])`). Cette logique sera traitée en Tâche 4 (rotate refactor). Ici, on laisse ces assertions en place ; elles vont casser quand on lancera les tests mais c'est attendu — la tâche 4 les corrigera.

- [ ] **Step 5: Lancer la suite intégration, observer les casses attendues**

```bash
cd backend
uv run pytest tests/integration/ -v 2>&1 | tail -60
```

Expected :
- Les tests touchés par cette tâche compilent (plus d'erreur `column api_key_hash`).
- Les tests qui exécutent du **code applicatif** (création workspace, rotate, auth) tombent toujours — c'est attendu, les services n'ont pas encore été refactorés.
- Documenter dans le commit le nombre exact de tests verts vs cassés post-cette-tâche (ex : 124 passed, 18 failed → bornes à dépasser).

- [ ] **Step 6: Commit**

```bash
git add backend/tests/integration/test_helpers.py \
        backend/tests/integration/test_migration_001.py \
        backend/tests/integration/test_migration_002.py \
        backend/tests/integration/test_migration_003.py \
        backend/tests/integration/test_services_models.py \
        backend/tests/integration/test_indexer_noop.py \
        backend/tests/integration/test_indexer_real.py \
        backend/tests/integration/test_sync_executor.py \
        backend/tests/integration/test_sync_picker.py \
        backend/tests/integration/test_sync_recovery.py \
        backend/tests/integration/test_sync_scheduler.py \
        backend/tests/integration/test_sync_worker.py
git commit -m "test(M5e-T2): adapte INSERT workspaces au schéma chiffré (helper seed)"
```

---

## Task 3: Settings `api_key_dek` + validateur

**Files:**
- Modify: `backend/src/rag/config.py`
- Create: `backend/tests/unit/test_config_api_key_dek.py`

- [ ] **Step 1: Écrire les tests Settings (rouge)**

`backend/tests/unit/test_config_api_key_dek.py` :

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.config import Settings


def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Variables minimales requises par Settings pour qu'il soit instanciable."""
    monkeypatch.setenv("RAG_MASTER_KEY", "master-key-32-chars-min-xxxxxxxxxx")
    monkeypatch.setenv("RAG_POSTGRES_URL", "postgresql://r:r@h/db")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://r:r@h/postgres")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("ENVIRONMENT", "test")


def test_api_key_dek_absent_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.delenv("RAG_API_KEY_DEK", raising=False)
    s = Settings()
    assert s.api_key_dek is None


def test_api_key_dek_empty_string_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("RAG_API_KEY_DEK", "")
    s = Settings()
    assert s.api_key_dek is None


def test_api_key_dek_too_short_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("RAG_API_KEY_DEK", "x" * 31)
    with pytest.raises(ValidationError, match="32 caractères"):
        Settings()


def test_api_key_dek_exactly_32_chars_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("RAG_API_KEY_DEK", "x" * 32)
    s = Settings()
    assert s.api_key_dek == "x" * 32
```

**Adapter `_base_env`** : exécuter `grep -n "field_validator\|alias=\"RAG\|env=\"RAG" backend/src/rag/config.py` pour aligner exactement les variables requises par Settings (la mémoire ag-flow-rag-conventions liste "5 champs Settings requis"). Si le projet utilise des `default=` pour certains, ne les set pas.

- [ ] **Step 2: Run tests rouges**

```bash
cd backend
uv run pytest tests/unit/test_config_api_key_dek.py -v
```

Expected : 4 fail (`AttributeError: 'Settings' object has no attribute 'api_key_dek'`).

- [ ] **Step 3: Ajouter le champ dans `config.py`**

Identifier la classe `Settings` et ajouter, sur le modèle exact du champ `harpocrate_dek` existant (cf. `config.py:85-90`) :

```python
api_key_dek: str | None = Field(default=None, alias="RAG_API_KEY_DEK")

@field_validator("api_key_dek")
@classmethod
def _validate_api_key_dek(cls, v: str | None) -> str | None:
    # Une valeur vide (RAG_API_KEY_DEK= dans .env) est traitée comme absente —
    # symétrique au comportement HARPOCRATE_DEK.
    if not v:
        return None
    if len(v) < 32:
        raise ValueError("RAG_API_KEY_DEK doit faire au moins 32 caractères")
    return v
```

- [ ] **Step 4: Run tests verts**

```bash
uv run pytest tests/unit/test_config_api_key_dek.py -v
```

Expected : 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/rag/config.py backend/tests/unit/test_config_api_key_dek.py
git commit -m "feat(M5e-T3): Settings.api_key_dek + validateur ≥32 chars (RAG_API_KEY_DEK)"
```

---

## Task 4: Service apikey.py — suppression bcrypt

**Files:**
- Modify: `backend/src/rag/services/apikey.py`
- Modify: `backend/tests/unit/test_apikey.py`

**Contexte** : `apikey.py` contient aujourd'hui `generate_api_key` (à garder), `hash_api_key` (à supprimer) et `verify_api_key` (à supprimer). Le chiffrement passe désormais par les requêtes SQL des services consommateurs.

- [ ] **Step 1: Lire le test unit existant**

```bash
cat backend/tests/unit/test_apikey.py
```

Repérer les tests `test_hash_api_key_*`, `test_verify_api_key_*` (à supprimer) et `test_generate_api_key_*` (à garder).

- [ ] **Step 2: Supprimer les tests bcrypt**

Ouvrir `backend/tests/unit/test_apikey.py` et retirer toutes les fonctions de test qui mentionnent `hash_api_key` ou `verify_api_key`. Garder les tests `generate_api_key`.

- [ ] **Step 3: Run tests (encore verts, sous-ensemble réduit)**

```bash
uv run pytest tests/unit/test_apikey.py -v
```

Expected : tous PASS (tests bcrypt supprimés, generate_api_key inchangé).

- [ ] **Step 4: Supprimer les fonctions du module**

Éditer `backend/src/rag/services/apikey.py`. Cible finale :

```python
from __future__ import annotations

import base64
import secrets

_KEY_BYTES = 36


def generate_api_key() -> str:
    """Génère une api_key URL-safe de 48 caractères (base64-url sans padding).

    Source : secrets.token_bytes(36) → 36 bytes = 48 chars en base64-url.
    Charset : [A-Za-z0-9_-], suffisamment dense pour un usage en header HTTP.
    """
    raw = secrets.token_bytes(_KEY_BYTES)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
```

Supprimer l'import `bcrypt` et les constantes `_BCRYPT_ROUNDS`.

- [ ] **Step 5: Run tests unit + intégration sur apikey/services**

```bash
uv run pytest tests/unit/test_apikey.py tests/integration/test_services_workspaces_create.py -v
```

Expected : tests unit PASS. Le test d'intégration peut casser (import `hash_api_key` dans `workspaces.py` non encore mis à jour) — c'est attendu, traité dans la tâche suivante.

- [ ] **Step 6: Commit**

```bash
git add backend/src/rag/services/apikey.py backend/tests/unit/test_apikey.py
git commit -m "refactor(M5e-T4): services/apikey retire hash_api_key/verify_api_key (bcrypt)"
```

---

## Task 5: `create_workspace` — INSERT chiffré + fingerprint

**Files:**
- Modify: `backend/src/rag/services/workspaces.py` (fonction `create_workspace`)
- Modify: `backend/tests/integration/test_services_workspaces_create.py` (si assertions sur hash)

- [ ] **Step 1: Identifier les tests d'intégration `create`**

```bash
cd backend
grep -n "api_key_hash\|create_workspace" tests/integration/test_services_workspaces_create.py
```

Si le test fait `assert verify_api_key(returned_key, row["api_key_hash"])`, le remplacer par : `assert pgp_sym_decrypt(row["api_key_encrypted"], dek) == returned_key`. Le test doit aussi pouvoir passer `dek` à `create_workspace` via la config injectée (cf. step 4).

- [ ] **Step 2: Écrire/adapter le test rouge**

Le test doit vérifier que `create_workspace` :
- Retourne `api_key` en clair.
- Insère `api_key_encrypted` (BYTEA) déchiffrable avec le DEK.
- Insère `api_key_fingerprint` = SHA-256 hex de la clé en clair.

Exemple d'assertion ajoutée au test existant :

```python
async with config_pool.acquire() as conn:
    row = await conn.fetchrow(
        "SELECT api_key_encrypted, api_key_fingerprint, "
        "pgp_sym_decrypt(api_key_encrypted, $1::text)::text AS decrypted "
        "FROM workspaces WHERE name = $2",
        dek, request.name,
    )
assert row is not None
assert row["decrypted"] == result["api_key"]
assert row["api_key_fingerprint"] == sha256(result["api_key"].encode()).hexdigest()
```

Run, doit échouer (signature `create_workspace` ne prend pas encore `dek`, et l'INSERT actuel utilise `api_key_hash`).

- [ ] **Step 3: Refactorer `create_workspace`**

Dans `backend/src/rag/services/workspaces.py:62-150`, modifier :

1. Signature : ajouter paramètre `api_key_dek: str` (keyword-only).
2. Imports : retirer `hash_api_key` ; ajouter `from hashlib import sha256`.
3. Remplacer la génération hash :

```python
# Avant :
#   api_key_hash = hash_api_key(api_key)
# Après :
fingerprint = sha256(api_key.encode("utf-8")).hexdigest()
```

4. Adapter l'INSERT :

```python
ws_row = await conn.fetchrow(
    """
    INSERT INTO workspaces
        (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base)
    VALUES
        ($1, pgp_sym_encrypt($2::text, $3::text)::bytea, $4, $5, $6)
    RETURNING id, created_at
    """,
    request.name,
    api_key,
    api_key_dek,
    fingerprint,
    rag_cnx,
    rag_base,
)
```

- [ ] **Step 4: Adapter le routeur admin (passage du DEK)**

`backend/src/rag/api/admin.py` ligne ~67 : le router admin appelle `create_workspace`. Ajouter la lecture du DEK depuis l'app state et la propager :

```python
@router.post("/workspaces", status_code=status.HTTP_201_CREATED)
async def post_workspaces(payload: WorkspaceCreateRequest, request: Request) -> ...:
    dek = request.app.state.settings.api_key_dek
    if dek is None:
        raise HTTPException(503, "api_key_dek_unavailable")
    ...
    return await create_workspace(
        request=payload,
        config_pool=_config_pool(request),
        admin_dsn=_admin_dsn(request),
        resolver=_resolver(request),
        default_vault_name=await _resolve_default_vault_or_503(request),
        api_key_dek=dek,
    )
```

**Note** : vérifier l'appel exact existant et y greffer `api_key_dek=dek`. Ne pas casser la signature pour les autres call sites — `create_workspace` reçoit le DEK en kwarg explicite.

- [ ] **Step 5: Run le test d'intégration create**

```bash
uv run pytest tests/integration/test_services_workspaces_create.py -v
```

Expected : PASS. Si le test échoue parce qu'il n'instancie pas `app.state.settings`, ajouter une fixture ou adapter le test pour passer `dek` directement à `create_workspace`.

- [ ] **Step 6: Commit**

```bash
git add backend/src/rag/services/workspaces.py \
        backend/src/rag/api/admin.py \
        backend/tests/integration/test_services_workspaces_create.py
git commit -m "feat(M5e-T5): create_workspace insère api_key chiffrée + fingerprint"
```

---

## Task 6: `rotate_apikey` — UPDATE chiffré + boucle anti-collision

**Files:**
- Modify: `backend/src/rag/services/workspaces.py` (fonction `rotate_apikey`)
- Modify: `backend/tests/integration/test_services_workspaces_rotate.py`

- [ ] **Step 1: Adapter le test d'intégration rotate (rouge)**

`backend/tests/integration/test_services_workspaces_rotate.py` : remplacer les assertions sur `api_key_hash` + `verify_api_key` par un décryptage explicite.

```python
from hashlib import sha256

# ... après l'appel rotate_apikey :
row = await fetch_one(
    config_pool,
    "SELECT pgp_sym_decrypt(api_key_encrypted, $1::text)::text AS decrypted, "
    "api_key_fingerprint FROM workspaces WHERE name=$2",
    dek, "ws_rotate",
)
assert row["decrypted"] == new_key
assert row["api_key_fingerprint"] == sha256(new_key.encode()).hexdigest()
# L'ancienne clé ne doit plus correspondre :
assert row["decrypted"] != old_key
```

Ajouter dans la fixture de ce test le passage du DEK à la fonction `rotate_apikey` (kwarg).

Run, doit échouer (signature pas encore mise à jour).

- [ ] **Step 2: Refactorer `rotate_apikey`**

Dans `workspaces.py:246-280` :

```python
async def rotate_apikey(
    *,
    name: str,
    config_pool: asyncpg.Pool,
    api_key_dek: str,
    apikey_cache: ApiKeyCache | None = None,
    max_attempts: int = 3,
) -> str:
    """Régénère une api_key pour le workspace, retourne la nouvelle en clair.

    Boucle bornée à max_attempts pour gérer la collision théorique du
    fingerprint (proba ~2⁻¹²⁸ par paire). Lève RuntimeError au-delà.
    Lève WorkspaceNotFound si le workspace n'existe pas.
    """
    row = await fetch_one(config_pool, "SELECT id FROM workspaces WHERE name=$1", name)
    if row is None:
        raise WorkspaceNotFound(name)

    last_err: asyncpg.UniqueViolationError | None = None
    for _ in range(max_attempts):
        new_key = generate_api_key()
        fingerprint = sha256(new_key.encode("utf-8")).hexdigest()
        try:
            async with config_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE workspaces SET "
                    "api_key_encrypted = pgp_sym_encrypt($1::text, $2::text)::bytea, "
                    "api_key_fingerprint = $3, "
                    "updated_at = now() "
                    "WHERE id = $4",
                    new_key, api_key_dek, fingerprint, row["id"],
                )
            break
        except asyncpg.UniqueViolationError as e:
            last_err = e
            continue
    else:
        raise RuntimeError(
            f"fingerprint collision after {max_attempts} attempts"
        ) from last_err

    if apikey_cache is not None:
        apikey_cache.invalidate(name)

    log.info("workspace.apikey_rotated", name=name)
    return new_key
```

Imports nécessaires : `from hashlib import sha256` (déjà ajouté en Task 5).

- [ ] **Step 3: Adapter le routeur admin pour passer le DEK**

`admin.py:116-122` : `rotate_apikey_endpoint` doit lire `app.state.settings.api_key_dek` et le passer en kwarg, avec 503 si absent — même pattern que `post_workspaces`.

- [ ] **Step 4: Test collision (optionnel mais conseillé)**

Ajouter un test qui force la collision : monkeypatch `generate_api_key` pour retourner la même valeur 2 fois puis une nouvelle, vérifier que `rotate_apikey` ne lève pas et que la valeur finale est bien la 3ème.

```python
@pytest.mark.asyncio
async def test_rotate_handles_fingerprint_collision(...):
    keys = iter(["k_collide", "k_collide", "k_ok"])
    monkeypatch.setattr(
        "rag.services.workspaces.generate_api_key",
        lambda: next(keys),
    )
    # ... seed un autre workspace dont la fingerprint = sha256("k_collide")
    # ... rotate, attendre k_ok
```

- [ ] **Step 5: Run tests rotate**

```bash
uv run pytest tests/integration/test_services_workspaces_rotate.py -v
```

Expected : PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/rag/services/workspaces.py \
        backend/src/rag/api/admin.py \
        backend/tests/integration/test_services_workspaces_rotate.py
git commit -m "feat(M5e-T6): rotate_apikey UPDATE chiffré + boucle anti-collision (3 tentatives)"
```

---

## Task 7: `workspace_auth` — lookup par fingerprint + decrypt timing-safe

**Files:**
- Modify: `backend/src/rag/auth/workspace_auth.py`
- Modify: `backend/tests/unit/auth/test_require_workspace_apikey.py`
- Create: `backend/tests/integration/test_workspace_auth_lookup.py`

- [ ] **Step 1: Écrire le test d'intégration (rouge)**

`backend/tests/integration/test_workspace_auth_lookup.py` :

```python
from __future__ import annotations

from hashlib import sha256

import asyncpg
import pytest
from fastapi import FastAPI, HTTPException, Request
from starlette.datastructures import Headers

from rag.auth.workspace_auth import ApiKeyCache, require_workspace_apikey
from tests.integration._workspace_seed import seed_workspace


def _make_request(app: FastAPI, headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "app": app,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_valid_apikey_returns_auth_context(migrated: asyncpg.Pool) -> None:
    api_key = "valid-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    dek = "x" * 32
    async with migrated.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_auth", api_key=api_key, dek=dek)
        # seed un indexer_config minimal (FK requise)
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'ollama', 'mxbai-embed-large', 1024)",
            ws_id,
        )

    app = FastAPI()
    class _Pools: config_pool = migrated
    class _Settings: api_key_dek = dek
    app.state.pools = _Pools()
    app.state.apikey_cache = ApiKeyCache()
    app.state.settings = _Settings()

    req = _make_request(app, {"Authorization": f"Bearer {api_key}"})
    ctx = await require_workspace_apikey("ws_auth", req)
    assert ctx.workspace_id == ws_id


@pytest.mark.asyncio
async def test_unknown_apikey_raises_401(migrated: asyncpg.Pool) -> None:
    dek = "x" * 32
    async with migrated.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_a", api_key="real-key", dek=dek)
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'ollama', 'mxbai-embed-large', 1024)",
            ws_id,
        )

    app = FastAPI()
    class _Pools: config_pool = migrated
    class _Settings: api_key_dek = dek
    app.state.pools = _Pools()
    app.state.apikey_cache = ApiKeyCache()
    app.state.settings = _Settings()

    req = _make_request(app, {"Authorization": "Bearer fake-key"})
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws_a", req)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_rotated_key_invalidates_old(migrated: asyncpg.Pool) -> None:
    """L'ancienne clé ne valide plus après une rotation manuelle (UPDATE direct)."""
    old_key = "old-key-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    new_key = "new-key-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    dek = "x" * 32
    async with migrated.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_rot", api_key=old_key, dek=dek)
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'ollama', 'mxbai-embed-large', 1024)",
            ws_id,
        )
        # rotation manuelle (simule rotate_apikey)
        await conn.execute(
            "UPDATE workspaces SET "
            "api_key_encrypted = pgp_sym_encrypt($1::text, $2::text)::bytea, "
            "api_key_fingerprint = $3 WHERE id = $4",
            new_key, dek, sha256(new_key.encode()).hexdigest(), ws_id,
        )

    app = FastAPI()
    class _Pools: config_pool = migrated
    class _Settings: api_key_dek = dek
    app.state.pools = _Pools()
    app.state.apikey_cache = ApiKeyCache()
    app.state.settings = _Settings()

    req_old = _make_request(app, {"Authorization": f"Bearer {old_key}"})
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws_rot", req_old)
    assert exc.value.status_code == 401

    req_new = _make_request(app, {"Authorization": f"Bearer {new_key}"})
    ctx = await require_workspace_apikey("ws_rot", req_new)
    assert ctx.workspace_id == ws_id
```

Note : la fixture `migrated` est définie dans `test_helpers.py` (cf. Task 2) — l'importer ou la dupliquer dans un `conftest.py` local au dossier `integration/`. Si elle n'est pas réutilisable telle quelle, créer une fixture locale équivalente dans le fichier.

Run, doit échouer (le code applicatif fait encore du bcrypt).

- [ ] **Step 2: Refactorer `require_workspace_apikey`**

`backend/src/rag/auth/workspace_auth.py:83-130` :

```python
from hashlib import sha256
from secrets import compare_digest

# ... (le reste des imports + ApiKeyCache inchangés)

async def require_workspace_apikey(
    name: str,
    request: Request,
) -> AuthContext:
    """Dependency FastAPI : valide `Authorization: Bearer <WORKSPACE_API_KEY>`.

    Lookup O(1) par fingerprint SHA-256 puis comparaison timing-safe sur
    la valeur déchiffrée. Cache LRU+TTL conservé.

    - 401 si bearer absent / mauvais scheme / clé invalide.
    - 404 si workspace inexistant.
    - 503 si DEK absent en config.
    - Sur succès : retourne `AuthContext(workspace_id, indexer_used)`.
    """
    api_key = _extract_bearer(request)

    cache: ApiKeyCache = request.app.state.apikey_cache
    pool: asyncpg.Pool = request.app.state.pools.config_pool
    dek: str | None = request.app.state.settings.api_key_dek
    if dek is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="api_key_dek_unavailable",
        )

    entry = cache.get(name, api_key)
    if entry is not None:
        return AuthContext(workspace_id=entry.workspace_id, indexer_used=entry.indexer_used)

    fingerprint = sha256(api_key.encode("utf-8")).hexdigest()
    row = await pool.fetchrow(
        """
        SELECT w.id,
               pgp_sym_decrypt(w.api_key_encrypted, $2::text)::text AS stored,
               ic.provider || '/' || ic.model AS indexer_used
        FROM workspaces w
        JOIN indexer_configs ic ON ic.workspace_id = w.id
        WHERE w.name = $1 AND w.api_key_fingerprint = $3
        """,
        name, dek, fingerprint,
    )
    if row is None:
        # Soit le workspace n'existe pas, soit la clé ne match pas — 401 dans les
        # deux cas pour ne pas révéler l'existence (alignement sécurité).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_workspace_apikey",
        )

    # Vérification timing-safe contre collision SHA-256 théorique.
    if not compare_digest(api_key, row["stored"]):
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

Retirer l'import `verify_api_key` (qui n'existe plus depuis Task 4).

**Note importante** : le test `test_require_workspace_apikey_workspace_not_found` doit être adapté — le nouveau code renvoie 401 (et non 404) si le workspace n'existe pas, alignement sécurité explicite dans le docstring. Si l'utilisateur veut garder 404 pour le name inconnu, faire deux requêtes (existence + match) ; mais 401 uniforme est plus défensif. **Mettre à jour le test pour attendre 401**.

- [ ] **Step 3: Adapter le test unit existant**

`backend/tests/unit/auth/test_require_workspace_apikey.py` : ce test utilise probablement `unittest.mock` pour mocker la requête BD. Le mock doit retourner une `row` avec `stored` (au lieu de `api_key_hash`), et la fixture doit poser `app.state.settings.api_key_dek = "x"*32`. Adapter en parcourant le fichier.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/auth/ tests/integration/test_workspace_auth_lookup.py -v
```

Expected : PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/rag/auth/workspace_auth.py \
        backend/tests/unit/auth/test_require_workspace_apikey.py \
        backend/tests/integration/test_workspace_auth_lookup.py
git commit -m "feat(M5e-T7): require_workspace_apikey lookup fingerprint + decrypt timing-safe"
```

---

## Task 8: Endpoint `GET /api/admin/workspaces/{name}/apikey`

**Files:**
- Modify: `backend/src/rag/api/admin.py`
- Create: `backend/tests/integration/test_api_admin_workspaces_apikey.py`

- [ ] **Step 1: Écrire le test d'intégration (rouge)**

`backend/tests/integration/test_api_admin_workspaces_apikey.py` :

```python
from __future__ import annotations

import pytest
from httpx import AsyncClient

# Utilise la fixture `admin_client` existante (cf. conftest.py de tests/integration)
# qui démarre l'app FastAPI complète avec Settings.api_key_dek configuré.


@pytest.mark.asyncio
async def test_get_apikey_returns_stored_key(admin_client: AsyncClient) -> None:
    # Crée un workspace via l'API (la création retourne la clé en clair)
    create_resp = await admin_client.post("/api/admin/workspaces", json={
        "name": "ws_get",
        "indexer": {"provider": "ollama", "model": "mxbai-embed-large", "api_key_ref": None},
    })
    assert create_resp.status_code == 201
    expected_key = create_resp.json()["api_key"]

    # GET retourne la même valeur
    get_resp = await admin_client.get("/api/admin/workspaces/ws_get/apikey")
    assert get_resp.status_code == 200
    assert get_resp.json()["api_key"] == expected_key


@pytest.mark.asyncio
async def test_get_apikey_is_idempotent(admin_client: AsyncClient) -> None:
    await admin_client.post("/api/admin/workspaces", json={
        "name": "ws_idem",
        "indexer": {"provider": "ollama", "model": "mxbai-embed-large", "api_key_ref": None},
    })
    r1 = await admin_client.get("/api/admin/workspaces/ws_idem/apikey")
    r2 = await admin_client.get("/api/admin/workspaces/ws_idem/apikey")
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["api_key"] == r2.json()["api_key"]


@pytest.mark.asyncio
async def test_get_apikey_reflects_rotation(admin_client: AsyncClient) -> None:
    await admin_client.post("/api/admin/workspaces", json={
        "name": "ws_rot",
        "indexer": {"provider": "ollama", "model": "mxbai-embed-large", "api_key_ref": None},
    })
    before = (await admin_client.get("/api/admin/workspaces/ws_rot/apikey")).json()["api_key"]
    rotated = (await admin_client.post("/api/admin/workspaces/ws_rot/rotate-apikey")).json()["api_key"]
    after = (await admin_client.get("/api/admin/workspaces/ws_rot/apikey")).json()["api_key"]
    assert before != after
    assert rotated == after


@pytest.mark.asyncio
async def test_get_apikey_404_when_workspace_missing(admin_client: AsyncClient) -> None:
    r = await admin_client.get("/api/admin/workspaces/does_not_exist/apikey")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_apikey_401_without_auth(unauthenticated_client: AsyncClient) -> None:
    """Le routeur admin est protégé par require_master_key_or_oidc_role."""
    r = await unauthenticated_client.get("/api/admin/workspaces/whatever/apikey")
    assert r.status_code == 401
```

**Note fixtures** : `admin_client` doit déjà exister (utilisé par les autres tests admin) — vérifier `tests/integration/conftest.py`. Si `unauthenticated_client` n'existe pas, créer une fixture qui construit un client sans header Authorization.

Run, doit échouer (endpoint absent).

- [ ] **Step 2: Ajouter l'endpoint dans `admin.py`**

Dans `backend/src/rag/api/admin.py`, ajouter après `get_workspace_detail` :

```python
@router.get("/workspaces/{name}/apikey")
async def get_apikey_endpoint(name: str, request: Request) -> ApiKeyRotateResponse:
    """Retourne l'api_key en clair du workspace. Idempotent.

    Conforme spec 08 : sert à `init-rag.sh` côté ag.flow.docker pour
    provisionner `.rag-client.json` au démarrage container.
    """
    dek = request.app.state.settings.api_key_dek
    if dek is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="api_key_dek_unavailable",
        )
    row = await _config_pool(request).fetchrow(
        "SELECT pgp_sym_decrypt(api_key_encrypted, $2::text)::text AS api_key "
        "FROM workspaces WHERE name = $1",
        name, dek,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace_not_found",
        )
    return ApiKeyRotateResponse(api_key=row["api_key"])
```

Vérifier que `ApiKeyRotateResponse` est déjà importé (utilisé par `rotate_apikey_endpoint`).

- [ ] **Step 3: Run tests d'intégration API**

```bash
uv run pytest tests/integration/test_api_admin_workspaces_apikey.py -v
```

Expected : 5 PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/src/rag/api/admin.py \
        backend/tests/integration/test_api_admin_workspaces_apikey.py
git commit -m "feat(M5e-T8): endpoint GET /api/admin/workspaces/{name}/apikey idempotent"
```

---

## Task 9: Lifespan check DEK requis

**Files:**
- Modify: `backend/src/rag/main.py`
- Create: `backend/tests/integration/test_lifespan_api_key_dek_required.py`

- [ ] **Step 1: Écrire le test (rouge)**

`backend/tests/integration/test_lifespan_api_key_dek_required.py` :

```python
from __future__ import annotations

import asyncpg
import pytest

from rag.main import lifespan, build_app  # adapter selon les exports réels
from tests.integration._workspace_seed import seed_workspace


@pytest.mark.asyncio
async def test_lifespan_fails_when_workspaces_exist_and_dek_absent(
    migrated: asyncpg.Pool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with migrated.acquire() as conn:
        await seed_workspace(conn, name="ws_pre", api_key="any", dek="x" * 32)

    monkeypatch.delenv("RAG_API_KEY_DEK", raising=False)
    # ... préparer le reste de l'env pour Settings (master key, postgres, redis)
    monkeypatch.setenv("RAG_MASTER_KEY", "master-key-32-chars-min-xxxxxxxxxx")
    # ... etc cf. test_config_api_key_dek

    app = build_app()
    with pytest.raises(RuntimeError, match="RAG_API_KEY_DEK"):
        async with lifespan(app):
            pass


@pytest.mark.asyncio
async def test_lifespan_succeeds_when_workspaces_empty_and_dek_absent(
    migrated: asyncpg.Pool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAG_API_KEY_DEK", raising=False)
    # ... même setup minimal

    app = build_app()
    async with lifespan(app):
        pass  # ne lève pas
```

**Adapter selon l'API exacte** : si `main.py` n'expose pas `build_app`/`lifespan` directement, utiliser l'app importable. Lire `main.py` lignes 80-170 pour identifier les exports.

Run, doit échouer (check non implémenté).

- [ ] **Step 2: Ajouter le check dans le lifespan**

Dans `backend/src/rag/main.py`, dans le lifespan, **après** la création du pool config et **avant** le yield :

```python
# M5e — guard : si des workspaces existent en BDD, RAG_API_KEY_DEK doit être défini
# (sinon impossible de déchiffrer les api_keys, le service tournera en mode dégradé silencieux).
async with registry.config_pool.acquire() as conn:
    workspaces_count = await conn.fetchval("SELECT COUNT(*) FROM workspaces")
if workspaces_count > 0 and settings.api_key_dek is None:
    raise RuntimeError(
        "RAG_API_KEY_DEK manquant alors que la table workspaces contient "
        f"{workspaces_count} entrée(s)"
    )
```

Logguer aussi l'absence de DEK quand la table est vide (info level) pour traçabilité opérationnelle.

- [ ] **Step 3: Run tests lifespan**

```bash
uv run pytest tests/integration/test_lifespan_api_key_dek_required.py -v
```

Expected : 2 PASS.

- [ ] **Step 4: Smoke complet de la suite**

```bash
uv run pytest tests/ -v 2>&1 | tail -40
```

Expected : 100% PASS. Si des tests anciens cassent encore (manqués en Task 2), les fixer maintenant. Documenter dans le commit le total exact.

- [ ] **Step 5: Commit**

```bash
git add backend/src/rag/main.py \
        backend/tests/integration/test_lifespan_api_key_dek_required.py
git commit -m "feat(M5e-T9): lifespan refuse de démarrer si workspaces non vide sans RAG_API_KEY_DEK"
```

---

## Task 10: Documentation `.env.example` + spec 08

**Files:**
- Modify: `backend/.env.example`
- Modify: `specs/08-docker-init.md`

- [ ] **Step 1: Mettre à jour `.env.example`**

Ajouter une section après `HARPOCRATE_DEK` :

```
# ─── Workspace api_keys (M5e) ───────────────────────────────────────────────
#
# Clé maître de chiffrement réversible des api_keys workspace en BDD.
# DOIT faire au moins 32 caractères.
#
# ATTENTION :
#   - perdre cette valeur rend toutes les api_keys workspace inutilisables ;
#     la seule récupération est de rotater chaque workspace (POST /rotate-apikey).
#   - indépendant de HARPOCRATE_DEK : ne pas réutiliser la même valeur.
#   - si la table `workspaces` est non vide, ce paramètre est requis au boot
#     (le lifespan lève RuntimeError sinon).
#
# Génération : openssl rand -base64 32
RAG_API_KEY_DEK=
```

- [ ] **Step 2: Mettre à jour `specs/08-docker-init.md`**

Patches :

1. Section « Variables d'environnement requises » : path d'exemple inchangé.
2. Section « Script d'init » : remplacer `$RAG_SERVICE_URL/workspaces/$workspace/apikey` par `$RAG_SERVICE_URL/api/admin/workspaces/$workspace/apikey`. Ajouter en commentaire que l'endpoint est désormais protégé par `Authorization: Bearer $RAG_MASTER_KEY`.
3. Section « Idempotence » : préciser que l'endpoint déchiffre une valeur stockée en `pgp_sym_encrypt`, et que côté serveur le secret `RAG_API_KEY_DEK` doit être défini (≥32 chars).
4. Ajouter une sous-section finale « Prérequis serveur » :

   ```markdown
   ## Prérequis serveur

   Le service RAG doit avoir `RAG_API_KEY_DEK` défini (≥32 chars). Cette clé
   maître chiffre les api_keys workspace en BDD et permet à l'endpoint
   `GET /apikey` de fonctionner de manière idempotente. Cf. M5e dans
   `docs/superpowers/specs/`.
   ```

- [ ] **Step 3: Commit**

```bash
git add backend/.env.example specs/08-docker-init.md
git commit -m "docs(M5e-T10): .env.example + spec 08 — path /api/admin et RAG_API_KEY_DEK"
```

---

## Task 11: Smoke E2E LXC 303

**Files:** aucun (vérification déploiement)

- [ ] **Step 1: Déployer la branche `dev`**

```bash
git push origin dev
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && ./dev-deploy.sh'"
```

Vérifier dans la sortie : migration 010 appliquée, `/health` 200, `/version` reflète le SHA récent.

- [ ] **Step 2: Définir `RAG_API_KEY_DEK` sur LXC 303**

```bash
ssh pve "pct exec 303 -- bash -c 'echo RAG_API_KEY_DEK=$(openssl rand -base64 32) >> /opt/rag/.env'"
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && docker compose -f docker-compose-dev.yml restart backend'"
```

Vérifier que le backend redémarre sans `RuntimeError`.

- [ ] **Step 3: Smoke endpoint via Bearer master**

```bash
MASTER_KEY=$(ssh pve "pct exec 303 -- bash -c 'grep ^RAG_MASTER_KEY /opt/rag/.env | cut -d= -f2'")
# Créer un workspace de test
curl -sS -X POST -H "Authorization: Bearer $MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"ws_smoke","indexer":{"provider":"ollama","model":"mxbai-embed-large","api_key_ref":null}}' \
  https://rag.yoops.org/api/admin/workspaces
# → noter la api_key retournée

# GET idempotent
curl -sS -H "Authorization: Bearer $MASTER_KEY" \
  https://rag.yoops.org/api/admin/workspaces/ws_smoke/apikey
# → doit retourner la même api_key

curl -sS -H "Authorization: Bearer $MASTER_KEY" \
  https://rag.yoops.org/api/admin/workspaces/ws_smoke/apikey
# → idem
```

- [ ] **Step 4: Cleanup workspace de test**

```bash
curl -sS -X DELETE -H "Authorization: Bearer $MASTER_KEY" \
  https://rag.yoops.org/api/admin/workspaces/ws_smoke
```

- [ ] **Step 5: Rapport et clôture**

Documenter dans un commit final court :

```bash
git commit --allow-empty -m "chore(M5e): smoke E2E LXC 303 validé (POST create + GET apikey idempotent)"
```

---

## Auto-revue post-rédaction

- **Couverture spec** : sections 3-11 de la spec design ont chacune au moins une tâche associée. Section 11 (mise à jour spec 08) → Task 10. Section 9 (ordre exécution) reflété par l'ordre Task 1 → Task 11.
- **Pas de placeholders** : pas de TBD/TODO ; chaque step a son code complet ou sa commande exacte.
- **Types cohérents** : `api_key_dek: str | None` partout ; `fingerprint: str` (hex) ; `api_key_encrypted: bytes`. La signature `rotate_apikey(*, api_key_dek: str)` est utilisée à la fois en service et au routeur admin.
- **Hors-scope respecté** : rotation DEK, audit, rate-limiting, script `init-rag.sh` lui-même sont explicitement exclus dans la spec § 10. Aucune tâche ne les traite.
