# M9 — Chunking infrastructure (backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer l'infrastructure de chunking par workspace : table `chunking_configs` obligatoire, ajout `embeddings.metadata jsonb` (migration des bases workspace au boot), restructuration `chunking/` en package avec `ChunkerProtocol` + factory, adaptation `RealIndexer` pour lire la config, flow de reindex sur changement de config (symétrique de l'indexer change). **Pas de nouvel algorithme** — seul `ParagraphChunker` est livré, encapsulant l'algo actuel.

**Architecture:** Pattern miroir de `indexer_configs` et `rerank_configs` côté config (CRUD asyncpg + endpoint admin). Pattern miroir de `indexer/providers/` côté chunkers (Protocol + factory). Nouvelle infra `workspace_migrations/` (runner idempotent + table de versionnage par base workspace) appelée au lifespan startup pour appliquer les migrations workspace manquantes (fail-fast).

**Tech Stack:** Python 3.12, asyncpg, Pydantic v2, pytest + pytest-asyncio, structlog. Patterns de référence : `backend/migrations/011_rerank_configs.sql`, `backend/src/rag/services/rerank_configs.py`, `backend/src/rag/indexer/providers/factory.py`.

**Spec design** : `docs/superpowers/specs/2026-05-18-M9-backend-chunking-infrastructure-design.md`

---

## File Structure

| Fichier | Statut | Responsabilité |
|---|---|---|
| `backend/migrations/012_chunking_configs.sql` | **Create** | Table chunking_configs + FK CASCADE + CHECKs + peuplement workspaces existants |
| `backend/migrations/013_index_jobs_chunking_change_trigger.sql` | **Create** | Élargit CHECK `index_jobs.triggered_by` avec `reindex_chunking_change` |
| `backend/src/rag/db/workspace_migrations/__init__.py` | **Create** | re-export `apply_pending` |
| `backend/src/rag/db/workspace_migrations/runner.py` | **Create** | Runner idempotent (workspace_schema_migrations + apply ordered) |
| `backend/src/rag/db/workspace_migrations/versions/001_embeddings_metadata.sql` | **Create** | `ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS metadata JSONB...` |
| `backend/src/rag/db/workspace_schema.py` | **Modify** | `create_embeddings_table` : ajout colonne `metadata` |
| `backend/src/rag/indexer/chunking.py` | **Delete** | Remplacé par le package `chunking/` |
| `backend/src/rag/indexer/chunking/__init__.py` | **Create** | re-export `Chunk`, `ChunkerProtocol`, `ParagraphChunker`, `make_chunker` |
| `backend/src/rag/indexer/chunking/protocol.py` | **Create** | `Chunk` dataclass + `ChunkerProtocol` |
| `backend/src/rag/indexer/chunking/paragraph.py` | **Create** | `ParagraphChunker` (algo actuel déplacé) |
| `backend/src/rag/indexer/chunking/factory.py` | **Create** | `make_chunker(strategy, **params)` |
| `backend/src/rag/schemas/admin.py` | **Modify** | +`ChunkingConfigSpec`, +`ChunkingConfigResponse` |
| `backend/src/rag/services/chunking_configs.py` | **Create** | `get_chunking_config`, `upsert_chunking_config` |
| `backend/src/rag/services/workspaces.py` | **Modify** | `create_workspace` insère row default + appelle `apply_pending` |
| `backend/src/rag/services/jobs.py` | **Modify** | +`apply_chunking_change` |
| `backend/src/rag/indexer/real.py` | **Modify** | `_load_workspace_context` JOIN chunking_configs, `index_file` utilise factory |
| `backend/src/rag/db/workspace_embeddings.py` | **Modify** | `upsert_chunks(chunks: list[Chunk])` + insert `metadata` |
| `backend/src/rag/api/admin.py` | **Modify** | +endpoints GET/PUT chunking-config |
| `backend/src/rag/api/errors.py` | **Modify** | +`ChunkingChangeRequiresReindex` |
| `backend/src/agflow/main.py` | **Modify** | Lifespan boot scan : `apply_pending` sur chaque workspace |
| `backend/tests/unit/test_chunking.py` | **Delete** | Remplacé par tests du package |
| `backend/tests/unit/indexer/__init__.py` | **Create** | empty package marker |
| `backend/tests/unit/indexer/test_chunking_paragraph.py` | **Create** | Reprend les tests existants sur `ParagraphChunker.chunk()` |
| `backend/tests/unit/indexer/test_chunking_factory.py` | **Create** | `make_chunker` happy path + erreurs |
| `backend/tests/unit/schemas/__init__.py` | **Create** (si absent) | empty package marker |
| `backend/tests/unit/schemas/test_chunking_config_schema.py` | **Create** | DTO Pydantic |
| `backend/tests/integration/test_migration_012_chunking_configs.py` | **Create** | Schéma + CHECKs + peuplement + idempotence |
| `backend/tests/integration/test_migration_013_chunking_trigger.py` | **Create** | CHECK triggered_by élargie |
| `backend/tests/integration/test_workspace_migrations_runner.py` | **Create** | runner : ordre, idempotence, fail-fast, transaction par migration |
| `backend/tests/integration/test_workspace_migration_001_embeddings_metadata.py` | **Create** | Migration sur base existante préserve les données |
| `backend/tests/integration/test_services_chunking_configs.py` | **Create** | get/upsert + FK cascade |
| `backend/tests/integration/test_create_workspace_with_chunking.py` | **Create** | create_workspace insère default + applique workspace migrations |
| `backend/tests/integration/test_indexer_real_with_chunking_config.py` | **Create** | RealIndexer lit la config + respecte max_chars |
| `backend/tests/api/test_admin_workspaces_chunking.py` | **Create** | GET/PUT/204/200/202/409/422 |
| `backend/tests/integration/test_boot_workspace_migrations.py` | **Create** | Lifespan applique migrations + fail-fast |
| `specs/09-roadmap.md` | **Modify** | Marquer M9 livré |

---

## Task 1 — Migration 012 `chunking_configs`

**Files:**
- Create: `backend/migrations/012_chunking_configs.sql`
- Create: `backend/tests/integration/test_migration_012_chunking_configs.py`

- [ ] **Step 1: Écrire les tests de schéma (rouge)**

`backend/tests/integration/test_migration_012_chunking_configs.py` :

```python
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def _reset(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS chunking_configs, rerank_configs, indexer_configs, "
            "workspace_sources, index_jobs, indexed_documents, "
            "workspaces, harpocrate_vaults, model_dimensions, "
            "schema_migrations CASCADE"
        )


@pytest.mark.asyncio
async def test_chunking_configs_columns(session_pool: asyncpg.Pool) -> None:
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]: r["data_type"]
            for r in await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'chunking_configs'"
            )
        }
    expected = {
        "workspace_id", "strategy", "max_chars", "min_chars",
        "overlap_chars", "extras", "created_at", "updated_at",
    }
    assert expected.issubset(cols.keys()), f"missing: {expected - cols.keys()}"
    assert cols["workspace_id"] == "uuid"
    assert cols["strategy"] == "text"
    assert cols["max_chars"] == "integer"
    assert cols["extras"] == "jsonb"


@pytest.mark.asyncio
async def test_chunking_configs_fk_cascade(session_pool: asyncpg.Pool) -> None:
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_cascade")
        await conn.execute(
            "INSERT INTO chunking_configs "
            "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
            "VALUES ($1, 'paragraph', 2000, 200, 200)",
            ws_id,
        )
        await conn.execute("DELETE FROM workspaces WHERE id = $1", ws_id)
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM chunking_configs WHERE workspace_id = $1", ws_id,
        )
    assert count == 0


@pytest.mark.asyncio
async def test_chunking_configs_check_strategy_paragraph_only(
    session_pool: asyncpg.Pool,
) -> None:
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_strategy_check")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO chunking_configs "
                "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
                "VALUES ($1, 'markdown', 2000, 200, 200)",
                ws_id,
            )


@pytest.mark.asyncio
async def test_chunking_configs_check_min_lt_max(session_pool: asyncpg.Pool) -> None:
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_min_max")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO chunking_configs "
                "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
                "VALUES ($1, 'paragraph', 200, 200, 50)",
                ws_id,
            )


@pytest.mark.asyncio
async def test_chunking_configs_check_overlap_lt_max(
    session_pool: asyncpg.Pool,
) -> None:
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_overlap_max")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO chunking_configs "
                "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
                "VALUES ($1, 'paragraph', 500, 100, 500)",
                ws_id,
            )


@pytest.mark.asyncio
async def test_chunking_configs_populates_existing_workspaces(
    session_pool: asyncpg.Pool,
) -> None:
    """La migration crée une row par défaut pour chaque workspace existant."""
    await _reset(session_pool)
    # On migre jusqu'à 011 puis on crée 2 workspaces, puis on applique 012.
    # Simplification : on applique tout d'un coup et on vérifie que les workspaces
    # créés AVANT 012 (donc inexistants) sont OK. Pour tester réellement la clause
    # INSERT...SELECT, on crée des workspaces APRÈS migrations puis on supprime la
    # row chunking_configs et on re-applique 012 manuellement.
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_a = await seed_workspace(conn, name="ws_pop_a")
        ws_b = await seed_workspace(conn, name="ws_pop_b")
        await conn.execute("DELETE FROM chunking_configs")

        sql = (Path(__file__).resolve().parents[2] / "migrations"
               / "012_chunking_configs.sql").read_text(encoding="utf-8")
        # On rejoue uniquement le INSERT (la CREATE TABLE existerait déjà).
        insert_sql = sql[sql.index("INSERT INTO"):]
        await conn.execute(insert_sql)

        rows = await conn.fetch(
            "SELECT workspace_id, strategy, max_chars, min_chars, overlap_chars "
            "FROM chunking_configs WHERE workspace_id IN ($1, $2) "
            "ORDER BY workspace_id", ws_a, ws_b,
        )

    assert len(rows) == 2
    for r in rows:
        assert r["strategy"] == "paragraph"
        assert r["max_chars"] == 2000
        assert r["min_chars"] == 200
        assert r["overlap_chars"] == 200
```

- [ ] **Step 2: Lancer le test pour confirmer l'échec**

Lancer : `cd backend && uv run pytest tests/integration/test_migration_012_chunking_configs.py -v`
Attendu : ÉCHEC avec `relation "chunking_configs" does not exist` (la migration n'existe pas encore).

- [ ] **Step 3: Écrire la migration**

`backend/migrations/012_chunking_configs.sql` :

```sql
-- Migration 012 — chunking_configs : config chunking par workspace (obligatoire)
--
-- 1 row par workspace. La row est créée à la création du workspace.
-- Migration peuple les workspaces existants avec la stratégie 'paragraph' + valeurs actuelles.
-- Cascade ON DELETE : suppression workspace → suppression chunking_config auto.

CREATE TABLE chunking_configs (
    workspace_id    UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    strategy        TEXT NOT NULL CHECK (strategy IN ('paragraph')),
    max_chars       INT  NOT NULL CHECK (max_chars  > 0),
    min_chars       INT  NOT NULL CHECK (min_chars  >= 0 AND min_chars < max_chars),
    overlap_chars   INT  NOT NULL CHECK (overlap_chars >= 0 AND overlap_chars < max_chars),
    extras          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO chunking_configs (workspace_id, strategy, max_chars, min_chars, overlap_chars)
SELECT id, 'paragraph', 2000, 200, 200
FROM workspaces
ON CONFLICT (workspace_id) DO NOTHING;
```

- [ ] **Step 4: Lancer les tests pour confirmer le passage**

Lancer : `cd backend && uv run pytest tests/integration/test_migration_012_chunking_configs.py -v`
Attendu : 6 tests PASS.

- [ ] **Step 5: Lint + format**

```bash
cd backend && uv run ruff check src/ tests/ && uv run ruff format src/ tests/ --check
```

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/012_chunking_configs.sql backend/tests/integration/test_migration_012_chunking_configs.py
git commit -m "feat(M9-T1): migration 012 chunking_configs + tests schema/CHECK/cascade"
```

---

## Task 2 — Infra `workspace_migrations` (runner + migration 001 + schéma `embeddings`)

**Files:**
- Create: `backend/src/rag/db/workspace_migrations/__init__.py`
- Create: `backend/src/rag/db/workspace_migrations/runner.py`
- Create: `backend/src/rag/db/workspace_migrations/versions/001_embeddings_metadata.sql`
- Modify: `backend/src/rag/db/workspace_schema.py`
- Create: `backend/tests/integration/test_workspace_migrations_runner.py`
- Create: `backend/tests/integration/test_workspace_migration_001_embeddings_metadata.py`

- [ ] **Step 1: Écrire le test du runner (rouge)**

`backend/tests/integration/test_workspace_migrations_runner.py` :

```python
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.workspace_migrations import apply_pending


async def _fresh_dbname(admin_dsn: str, name: str) -> str:
    """Crée une base de test isolée et la retourne (caller doit drop)."""
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()
    return name


def _workspace_dsn(admin_dsn: str, dbname: str) -> str:
    # Reuse derive_workspace_dsn pour rester DRY
    from rag.db.workspace_schema import derive_workspace_dsn
    return derive_workspace_dsn(admin_dsn, dbname)


@pytest.mark.asyncio
async def test_apply_pending_creates_versioning_table(admin_dsn: str) -> None:
    name = await _fresh_dbname(admin_dsn, "rag_wsm_create_versioning")
    dsn = _workspace_dsn(admin_dsn, name)
    try:
        # Pas de table embeddings (cas dégénéré : versioning sans migration applicable)
        # mais on doit malgré tout créer workspace_schema_migrations sans planter.
        # On crée d'abord la table embeddings minimale (sans metadata) pour permettre
        # la migration 001 d'être appliquée.
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(
                "CREATE TABLE embeddings ("
                "id SERIAL PRIMARY KEY, path TEXT NOT NULL, "
                "chunk_index INT NOT NULL, content TEXT NOT NULL, "
                "indexed_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
        finally:
            await conn.close()

        applied = await apply_pending(dsn)
        assert applied == 1  # 001_embeddings_metadata

        # Re-run idempotent
        applied_again = await apply_pending(dsn)
        assert applied_again == 0

        conn = await asyncpg.connect(dsn)
        try:
            version = await conn.fetchval(
                "SELECT MAX(version) FROM workspace_schema_migrations"
            )
            assert version == 1
        finally:
            await conn.close()
    finally:
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()


@pytest.mark.asyncio
async def test_apply_pending_idempotent_on_pristine(admin_dsn: str) -> None:
    """Pas de table embeddings + run du runner : crée juste la table de versioning, applique 0 migration ou plante.

    Comportement attendu : on applique 1 migration (001), MAIS la migration utilise
    ALTER TABLE embeddings — qui plante si la table n'existe pas. On VEUT que ça
    plante en fail-fast. C'est le comportement § 6.4 de la spec.
    """
    name = await _fresh_dbname(admin_dsn, "rag_wsm_pristine")
    dsn = _workspace_dsn(admin_dsn, name)
    try:
        with pytest.raises(asyncpg.UndefinedTableError):
            await apply_pending(dsn)

        # Vérifie que la table de versioning a été créée malgré l'échec
        conn = await asyncpg.connect(dsn)
        try:
            exists = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'workspace_schema_migrations')"
            )
            assert exists is True
            # Mais aucune version n'est enregistrée (transaction rollback)
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM workspace_schema_migrations"
            )
            assert count == 0
        finally:
            await conn.close()
    finally:
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()
```

Note : la fixture `admin_dsn` doit être ajoutée dans `tests/integration/conftest.py` si elle n'existe pas. Vérifier d'abord (`grep -r "admin_dsn" backend/tests/integration/conftest.py`) ; sinon créer une fixture qui retourne `Settings().admin_postgres_dsn` ou équivalent (la lire depuis `Settings()` configuré pour les tests).

- [ ] **Step 2: Écrire le test de la migration 001 (rouge, viendra avec la 1)**

`backend/tests/integration/test_workspace_migration_001_embeddings_metadata.py` :

```python
from __future__ import annotations

import asyncpg
import pytest

from rag.db.workspace_migrations import apply_pending


async def _create_legacy_workspace_db(admin_dsn: str, name: str) -> str:
    """Crée une base workspace 'ancien schéma' : embeddings SANS la colonne metadata."""
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()

    from rag.db.workspace_schema import derive_workspace_dsn
    dsn = derive_workspace_dsn(admin_dsn, name)
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(
            "CREATE TABLE embeddings ("
            "id SERIAL PRIMARY KEY, path TEXT NOT NULL, "
            "chunk_index INT NOT NULL, content TEXT NOT NULL, "
            "embedding vector(8) NOT NULL, "
            "indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
            "UNIQUE (path, chunk_index))"
        )
        # Données existantes à préserver
        await conn.execute(
            "INSERT INTO embeddings (path, chunk_index, content, embedding) "
            "VALUES ('a.md', 0, 'hello', $1)",
            [0.0] * 8,
        )
    finally:
        await conn.close()
    return dsn


@pytest.mark.asyncio
async def test_migration_001_adds_metadata_column_preserves_data(
    admin_dsn: str,
) -> None:
    name = "rag_wsm_001_data"
    dsn = await _create_legacy_workspace_db(admin_dsn, name)
    try:
        await apply_pending(dsn)

        conn = await asyncpg.connect(dsn)
        try:
            cols = {
                r["column_name"]: r["data_type"]
                for r in await conn.fetch(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = 'embeddings'"
                )
            }
            assert "metadata" in cols
            assert cols["metadata"] == "jsonb"

            row = await conn.fetchrow(
                "SELECT content, metadata FROM embeddings WHERE path = 'a.md'"
            )
            assert row is not None
            assert row["content"] == "hello"
            assert row["metadata"] == "{}"  # jsonb default
        finally:
            await conn.close()
    finally:
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()
```

- [ ] **Step 3: Lancer les tests pour confirmer l'échec**

Lancer : `cd backend && uv run pytest tests/integration/test_workspace_migrations_runner.py tests/integration/test_workspace_migration_001_embeddings_metadata.py -v`
Attendu : ÉCHEC `ModuleNotFoundError: No module named 'rag.db.workspace_migrations'`.

- [ ] **Step 4: Écrire la migration 001**

`backend/src/rag/db/workspace_migrations/versions/001_embeddings_metadata.sql` :

```sql
ALTER TABLE embeddings
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
```

- [ ] **Step 5: Écrire le runner**

`backend/src/rag/db/workspace_migrations/__init__.py` :

```python
from __future__ import annotations

from .runner import apply_pending

__all__ = ["apply_pending"]
```

`backend/src/rag/db/workspace_migrations/runner.py` :

```python
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import asyncpg
import structlog

log = structlog.get_logger(__name__)

VERSIONS_DIR = Path(__file__).parent / "versions"
_FILENAME_RE = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")


def _list_versions() -> list[tuple[int, Path]]:
    """Retourne [(version, path)] triés par version croissante (I/O bloquante)."""
    out: list[tuple[int, Path]] = []
    for p in sorted(VERSIONS_DIR.iterdir()):
        if not p.is_file():
            continue
        m = _FILENAME_RE.match(p.name)
        if not m:
            raise RuntimeError(
                f"workspace migration filename does not match NNN_description.sql: {p.name}"
            )
        out.append((int(m.group(1)), p))
    return out


def _read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


async def apply_pending(workspace_dsn: str) -> int:
    """Applique les migrations workspace manquantes sur `workspace_dsn`.

    Idempotent. Crée `workspace_schema_migrations` si absente, lit la version
    courante, applique en ordre numérique les migrations > version courante.
    Chaque migration s'exécute dans sa propre transaction : si elle échoue, la
    transaction de cette migration est rollback ET l'exception remonte
    (fail-fast). Les migrations précédentes restent appliquées.

    Retourne le nombre de migrations appliquées dans cet appel.
    """
    conn = await asyncpg.connect(workspace_dsn)
    try:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS workspace_schema_migrations ("
            "version INT PRIMARY KEY, "
            "applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        current = await conn.fetchval(
            "SELECT COALESCE(MAX(version), 0) FROM workspace_schema_migrations"
        )

        versions = await asyncio.to_thread(_list_versions)
        pending = [(v, p) for v, p in versions if v > current]

        applied_count = 0
        for version, path in pending:
            sql = await asyncio.to_thread(_read_sql, path)
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO workspace_schema_migrations (version) VALUES ($1)",
                    version,
                )
            log.info("workspace_migration.applied", version=version, file=path.name)
            applied_count += 1

        return applied_count
    finally:
        await conn.close()
```

- [ ] **Step 6: Modifier `create_embeddings_table` pour inclure `metadata`**

`backend/src/rag/db/workspace_schema.py` (méthode `create_embeddings_table`) : remplacer le `CREATE TABLE embeddings` :

```python
await conn.execute(
    f"""
    CREATE TABLE embeddings (
        id           SERIAL PRIMARY KEY,
        path         TEXT NOT NULL,
        chunk_index  INT  NOT NULL,
        content      TEXT NOT NULL,
        embedding    vector({dimension}) NOT NULL,
        metadata     JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        indexed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (path, chunk_index)
    )
    """
)
```

Note : f-string → doubler les accolades JSONB `'{{}}'::jsonb`.

- [ ] **Step 7: Ajouter la fixture `admin_dsn` si absente**

Lancer : `grep -rn "admin_dsn" backend/tests/integration/conftest.py`
Si absent, l'ajouter dans `backend/tests/integration/conftest.py` :

```python
@pytest.fixture
def admin_dsn() -> str:
    """DSN admin pour créer/supprimer des bases workspace de test."""
    from rag.config import Settings
    return Settings().admin_postgres_dsn
```

(Si le nom du champ diffère dans `Settings`, l'adapter — vérifier `backend/src/rag/config.py`.)

- [ ] **Step 8: Lancer les tests pour confirmer le passage**

Lancer : `cd backend && uv run pytest tests/integration/test_workspace_migrations_runner.py tests/integration/test_workspace_migration_001_embeddings_metadata.py -v`
Attendu : tests PASS.

- [ ] **Step 9: Lint + format**

```bash
cd backend && uv run ruff check src/ tests/ && uv run ruff format src/ tests/ --check
```

- [ ] **Step 10: Commit**

```bash
git add backend/src/rag/db/workspace_migrations/ backend/src/rag/db/workspace_schema.py backend/tests/integration/test_workspace_migrations_runner.py backend/tests/integration/test_workspace_migration_001_embeddings_metadata.py backend/tests/integration/conftest.py
git commit -m "feat(M9-T2): infra workspace_migrations (runner + migration 001 embeddings.metadata)"
```

---

## Task 3 — Package `chunking/` (Protocol + Paragraph + Factory)

**Files:**
- Delete: `backend/src/rag/indexer/chunking.py`
- Delete: `backend/tests/unit/test_chunking.py`
- Create: `backend/src/rag/indexer/chunking/__init__.py`
- Create: `backend/src/rag/indexer/chunking/protocol.py`
- Create: `backend/src/rag/indexer/chunking/paragraph.py`
- Create: `backend/src/rag/indexer/chunking/factory.py`
- Create: `backend/tests/unit/indexer/__init__.py`
- Create: `backend/tests/unit/indexer/test_chunking_paragraph.py`
- Create: `backend/tests/unit/indexer/test_chunking_factory.py`

- [ ] **Step 1: Écrire les tests `ParagraphChunker` (rouge)**

`backend/tests/unit/indexer/__init__.py` : fichier vide.

`backend/tests/unit/indexer/test_chunking_paragraph.py` : porte tous les tests existants de `tests/unit/test_chunking.py` sur la nouvelle interface.

```python
from __future__ import annotations

import pytest

from rag.indexer.chunking import Chunk, ParagraphChunker


def _default() -> ParagraphChunker:
    return ParagraphChunker(max_chars=2000, min_chars=200, overlap_chars=200)


def test_empty_returns_empty() -> None:
    assert _default().chunk("") == []


def test_whitespace_only_returns_empty() -> None:
    assert _default().chunk("   \n\n   \n\n   ") == []


def test_short_content_returns_single_chunk() -> None:
    result = _default().chunk("hello world")
    assert len(result) == 1
    assert result[0].content == "hello world"
    assert result[0].metadata == {}


def test_two_short_paragraphs_are_coalesced() -> None:
    content = "Paragraphe un.\n\nParagraphe deux."
    result = _default().chunk(content)
    assert len(result) == 1
    assert "Paragraphe un." in result[0].content
    assert "Paragraphe deux." in result[0].content
    assert result[0].metadata == {}


def test_two_long_paragraphs_split_with_overlap() -> None:
    para_a = "A" * 1500
    para_b = "B" * 1500
    content = f"{para_a}\n\n{para_b}"
    result = ParagraphChunker(
        max_chars=2000, min_chars=200, overlap_chars=200,
    ).chunk(content)
    assert len(result) >= 2
    contents = [c.content for c in result]
    for i in range(1, len(contents)):
        assert any(
            contents[i].startswith(contents[i - 1][-k:]) for k in range(50, 201)
        )
    for c in result:
        assert c.metadata == {}


def test_giant_paragraph_split_on_separator() -> None:
    content = "Phrase courte. " * 200
    result = ParagraphChunker(
        max_chars=2000, min_chars=200, overlap_chars=200,
    ).chunk(content)
    assert len(result) >= 2
    for c in result:
        assert len(c.content) <= 2200
        assert c.metadata == {}


def test_code_no_paragraph_splits_on_newline() -> None:
    content = "\n".join([f"line {i}" for i in range(500)])
    result = ParagraphChunker(
        max_chars=2000, min_chars=200, overlap_chars=200,
    ).chunk(content)
    assert len(result) >= 2


def test_overlap_ge_max_raises() -> None:
    with pytest.raises(ValueError, match="overlap_chars"):
        ParagraphChunker(max_chars=200, min_chars=50, overlap_chars=200).chunk("x")


def test_chunk_metadata_is_always_empty_dict() -> None:
    chunks = _default().chunk("alpha\n\nbeta gamma\n\ndelta")
    for c in chunks:
        assert isinstance(c, Chunk)
        assert c.metadata == {}
```

- [ ] **Step 2: Écrire les tests `make_chunker` (rouge)**

`backend/tests/unit/indexer/test_chunking_factory.py` :

```python
from __future__ import annotations

import pytest

from rag.indexer.chunking import ParagraphChunker, make_chunker


def test_make_chunker_paragraph_returns_paragraph_chunker() -> None:
    chunker = make_chunker(
        strategy="paragraph",
        max_chars=1500, min_chars=150, overlap_chars=150,
        extras={},
    )
    assert isinstance(chunker, ParagraphChunker)


def test_make_chunker_paragraph_uses_params() -> None:
    chunker = make_chunker(
        strategy="paragraph",
        max_chars=500, min_chars=50, overlap_chars=50,
        extras={},
    )
    # Comportement observable : un texte de 1200 chars doit produire >= 2 chunks
    chunks = chunker.chunk("Phrase. " * 200)
    assert len(chunks) >= 2


def test_make_chunker_unknown_strategy_raises() -> None:
    with pytest.raises(ValueError, match="unknown chunking strategy: foo"):
        make_chunker(
            strategy="foo",
            max_chars=1000, min_chars=100, overlap_chars=100,
            extras={},
        )


def test_make_chunker_paragraph_rejects_non_empty_extras() -> None:
    with pytest.raises(ValueError, match="paragraph strategy does not accept extras"):
        make_chunker(
            strategy="paragraph",
            max_chars=1000, min_chars=100, overlap_chars=100,
            extras={"foo": "bar"},
        )
```

- [ ] **Step 3: Lancer les tests pour confirmer l'échec**

Lancer : `cd backend && uv run pytest tests/unit/indexer/ -v`
Attendu : ÉCHEC `ModuleNotFoundError: No module named 'rag.indexer.chunking'` (le fichier `chunking.py` n'a pas encore été remplacé par le package).

- [ ] **Step 4: Écrire le Protocol et la dataclass `Chunk`**

`backend/src/rag/indexer/chunking/protocol.py` :

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Chunk:
    """Un chunk produit par un chunker. `metadata` est vide pour ParagraphChunker."""

    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ChunkerProtocol(Protocol):
    def chunk(self, content: str) -> list[Chunk]: ...
```

- [ ] **Step 5: Écrire `ParagraphChunker` (déplacement de l'algo existant)**

`backend/src/rag/indexer/chunking/paragraph.py` :

```python
from __future__ import annotations

from rag.indexer.chunking.protocol import Chunk


class ParagraphChunker:
    """Découpe un texte par paragraphes, avec coalesce des petits + split des gros + overlap.

    Encapsule l'algorithme historique de `chunk_text` (M4a). `metadata` reste vide.
    """

    def __init__(
        self,
        *,
        max_chars: int,
        min_chars: int,
        overlap_chars: int,
    ) -> None:
        self._max_chars = max_chars
        self._min_chars = min_chars
        self._overlap_chars = overlap_chars

    def chunk(self, content: str) -> list[Chunk]:
        if self._overlap_chars >= self._max_chars:
            raise ValueError(
                f"overlap_chars ({self._overlap_chars}) must be < "
                f"max_chars ({self._max_chars})"
            )

        stripped = content.strip()
        if not stripped:
            return []

        paragraphs = [p.strip() for p in stripped.split("\n\n") if p.strip()]
        if len(paragraphs) == 1 and len(paragraphs[0]) > self._max_chars:
            paragraphs = [p for p in paragraphs[0].split("\n") if p.strip()]

        coalesced: list[str] = []
        buffer = ""
        for p in paragraphs:
            if not buffer:
                buffer = p
                continue
            if (
                len(buffer) < self._min_chars
                and len(buffer) + 2 + len(p) <= self._max_chars
            ):
                buffer = f"{buffer}\n\n{p}"
            else:
                coalesced.append(buffer)
                buffer = p
        if buffer:
            coalesced.append(buffer)

        split_chunks: list[str] = []
        for p in coalesced:
            if len(p) <= self._max_chars:
                split_chunks.append(p)
                continue
            split_chunks.extend(self._split_big_paragraph(p))

        if self._overlap_chars <= 0 or len(split_chunks) <= 1:
            return [Chunk(content=s) for s in split_chunks]

        result: list[Chunk] = [Chunk(content=split_chunks[0])]
        for i in range(1, len(split_chunks)):
            prev_tail = split_chunks[i - 1][-self._overlap_chars :]
            result.append(Chunk(content=prev_tail + split_chunks[i]))
        return result

    def _split_big_paragraph(self, p: str) -> list[str]:
        chunks: list[str] = []
        remaining = p
        while len(remaining) > self._max_chars:
            window_start = max(0, self._max_chars - 200)
            window = remaining[window_start : self._max_chars]
            cut_pos = -1
            for sep in (". ", "\n", " "):
                idx = window.rfind(sep)
                if idx != -1:
                    cut_pos = window_start + idx + len(sep)
                    break
            if cut_pos == -1:
                cut_pos = self._max_chars
            chunks.append(remaining[:cut_pos].strip())
            remaining = remaining[cut_pos:].lstrip()
        if remaining:
            chunks.append(remaining)
        return chunks
```

- [ ] **Step 6: Écrire la factory**

`backend/src/rag/indexer/chunking/factory.py` :

```python
from __future__ import annotations

from typing import Any

from rag.indexer.chunking.paragraph import ParagraphChunker
from rag.indexer.chunking.protocol import ChunkerProtocol


def make_chunker(
    *,
    strategy: str,
    max_chars: int,
    min_chars: int,
    overlap_chars: int,
    extras: dict[str, Any],
) -> ChunkerProtocol:
    if strategy == "paragraph":
        if extras:
            raise ValueError(
                f"paragraph strategy does not accept extras (got {extras!r})"
            )
        return ParagraphChunker(
            max_chars=max_chars,
            min_chars=min_chars,
            overlap_chars=overlap_chars,
        )
    raise ValueError(f"unknown chunking strategy: {strategy}")
```

- [ ] **Step 7: Écrire le `__init__.py` du package**

`backend/src/rag/indexer/chunking/__init__.py` :

```python
from __future__ import annotations

from rag.indexer.chunking.factory import make_chunker
from rag.indexer.chunking.paragraph import ParagraphChunker
from rag.indexer.chunking.protocol import Chunk, ChunkerProtocol

__all__ = ["Chunk", "ChunkerProtocol", "ParagraphChunker", "make_chunker"]
```

- [ ] **Step 8: Supprimer les anciens fichiers**

```bash
rm backend/src/rag/indexer/chunking.py
rm backend/tests/unit/test_chunking.py
```

- [ ] **Step 9: Lancer les tests pour confirmer le passage**

Lancer : `cd backend && uv run pytest tests/unit/indexer/ -v`
Attendu : tous tests PASS.

⚠️ À ce stade, `RealIndexer` importe encore `from rag.indexer.chunking import chunk_text` qui n'existe plus comme fonction. La modif viendra en Task 6 — pour l'instant la suite de tests d'intégration indexer va probablement échouer. C'est attendu et résolu en Task 6.

- [ ] **Step 10: Lint + format**

```bash
cd backend && uv run ruff check src/ tests/ && uv run ruff format src/ tests/ --check
```

- [ ] **Step 11: Commit**

```bash
git add backend/src/rag/indexer/chunking/ backend/src/rag/indexer/chunking.py backend/tests/unit/indexer/ backend/tests/unit/test_chunking.py
git commit -m "refactor(M9-T3): chunking.py → package chunking/ (Protocol + Paragraph + factory)"
```

---

## Task 4 — DTO Pydantic `ChunkingConfigSpec` + `ChunkingConfigResponse`

**Files:**
- Modify: `backend/src/rag/schemas/admin.py`
- Create: `backend/tests/unit/schemas/__init__.py` (si absent)
- Create: `backend/tests/unit/schemas/test_chunking_config_schema.py`

- [ ] **Step 1: Écrire les tests Pydantic (rouge)**

`backend/tests/unit/schemas/__init__.py` : fichier vide (vérifier d'abord s'il existe déjà).

`backend/tests/unit/schemas/test_chunking_config_schema.py` :

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.schemas.admin import ChunkingConfigSpec


def test_paragraph_happy_path() -> None:
    spec = ChunkingConfigSpec(
        strategy="paragraph", max_chars=2000, min_chars=200,
        overlap_chars=200, extras={},
    )
    assert spec.strategy == "paragraph"
    assert spec.max_chars == 2000


def test_max_chars_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ChunkingConfigSpec(
            strategy="paragraph", max_chars=0, min_chars=0,
            overlap_chars=0, extras={},
        )


def test_min_chars_must_be_lt_max_chars() -> None:
    with pytest.raises(ValidationError):
        ChunkingConfigSpec(
            strategy="paragraph", max_chars=200, min_chars=200,
            overlap_chars=50, extras={},
        )


def test_overlap_chars_must_be_lt_max_chars() -> None:
    with pytest.raises(ValidationError):
        ChunkingConfigSpec(
            strategy="paragraph", max_chars=500, min_chars=100,
            overlap_chars=500, extras={},
        )


def test_strategy_must_be_paragraph() -> None:
    with pytest.raises(ValidationError):
        ChunkingConfigSpec(
            strategy="markdown", max_chars=2000, min_chars=200,
            overlap_chars=200, extras={},
        )


def test_extras_must_be_empty_for_paragraph() -> None:
    with pytest.raises(ValidationError):
        ChunkingConfigSpec(
            strategy="paragraph", max_chars=2000, min_chars=200,
            overlap_chars=200, extras={"foo": "bar"},
        )


def test_min_chars_can_be_zero() -> None:
    spec = ChunkingConfigSpec(
        strategy="paragraph", max_chars=1000, min_chars=0,
        overlap_chars=100, extras={},
    )
    assert spec.min_chars == 0


def test_overlap_chars_can_be_zero() -> None:
    spec = ChunkingConfigSpec(
        strategy="paragraph", max_chars=1000, min_chars=100,
        overlap_chars=0, extras={},
    )
    assert spec.overlap_chars == 0
```

- [ ] **Step 2: Lancer les tests pour confirmer l'échec**

Lancer : `cd backend && uv run pytest tests/unit/schemas/test_chunking_config_schema.py -v`
Attendu : ÉCHEC `ImportError: cannot import name 'ChunkingConfigSpec'`.

- [ ] **Step 3: Ajouter les DTO dans `schemas/admin.py`**

Dans `backend/src/rag/schemas/admin.py`, ajouter en fin de fichier :

```python
from datetime import datetime


class ChunkingConfigSpec(BaseModel):
    """Payload PUT /workspaces/{name}/chunking-config."""

    model_config = ConfigDict(extra="forbid")

    strategy: Literal["paragraph"]
    max_chars: int = Field(gt=0)
    min_chars: int = Field(ge=0)
    overlap_chars: int = Field(ge=0)
    extras: dict[str, Any] = Field(default_factory=dict)

    @field_validator("min_chars")
    @classmethod
    def _min_lt_max(cls, v: int, info: Any) -> int:
        max_chars = info.data.get("max_chars")
        if max_chars is not None and v >= max_chars:
            raise ValueError("min_chars must be < max_chars")
        return v

    @field_validator("overlap_chars")
    @classmethod
    def _overlap_lt_max(cls, v: int, info: Any) -> int:
        max_chars = info.data.get("max_chars")
        if max_chars is not None and v >= max_chars:
            raise ValueError("overlap_chars must be < max_chars")
        return v

    @field_validator("extras")
    @classmethod
    def _extras_empty_for_paragraph(
        cls, v: dict[str, Any], info: Any,
    ) -> dict[str, Any]:
        if info.data.get("strategy") == "paragraph" and v:
            raise ValueError("extras must be empty for strategy 'paragraph'")
        return v


class ChunkingConfigResponse(BaseModel):
    """Réponse GET /workspaces/{name}/chunking-config."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    strategy: str
    max_chars: int
    min_chars: int
    overlap_chars: int
    extras: dict[str, Any]
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 4: Lancer les tests pour confirmer le passage**

Lancer : `cd backend && uv run pytest tests/unit/schemas/test_chunking_config_schema.py -v`
Attendu : 8 tests PASS.

- [ ] **Step 5: Lint + format + typecheck**

```bash
cd backend && uv run ruff check src/ tests/ && uv run ruff format src/ tests/ --check
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/rag/schemas/admin.py backend/tests/unit/schemas/
git commit -m "feat(M9-T4): DTO ChunkingConfigSpec + ChunkingConfigResponse (Pydantic)"
```

---

## Task 5 — Service `chunking_configs` (get/upsert)

**Files:**
- Create: `backend/src/rag/services/chunking_configs.py`
- Create: `backend/tests/integration/test_services_chunking_configs.py`

- [ ] **Step 1: Écrire les tests service (rouge)**

`backend/tests/integration/test_services_chunking_configs.py` :

```python
from __future__ import annotations

import asyncpg
import pytest

from rag.services.chunking_configs import (
    ChunkingConfigNotFound,
    get_chunking_config,
    upsert_chunking_config,
)
from tests.integration._workspace_seed import seed_workspace


@pytest.fixture
async def workspace_id(migrated: asyncpg.Pool) -> str:
    async with migrated.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_chunking_svc")
        # Le hook create_workspace insérera automatiquement la default row en
        # Task 5b. Pour ce test (service pur), on l'insère manuellement.
        await conn.execute(
            "INSERT INTO chunking_configs "
            "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
            "VALUES ($1, 'paragraph', 2000, 200, 200)",
            ws_id,
        )
    return ws_id


@pytest.mark.asyncio
async def test_get_returns_row(migrated: asyncpg.Pool, workspace_id: str) -> None:
    cfg = await get_chunking_config(workspace_id, migrated)
    assert cfg["strategy"] == "paragraph"
    assert cfg["max_chars"] == 2000
    assert cfg["min_chars"] == 200
    assert cfg["overlap_chars"] == 200
    assert cfg["extras"] == {}


@pytest.mark.asyncio
async def test_get_raises_when_missing(migrated: asyncpg.Pool) -> None:
    async with migrated.acquire() as conn:
        orphan_ws_id = await seed_workspace(conn, name="ws_no_config")
    with pytest.raises(ChunkingConfigNotFound):
        await get_chunking_config(orphan_ws_id, migrated)


@pytest.mark.asyncio
async def test_upsert_updates_existing(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    cfg = await upsert_chunking_config(
        migrated,
        workspace_id=workspace_id,
        strategy="paragraph",
        max_chars=1500, min_chars=100, overlap_chars=150,
        extras={},
    )
    assert cfg["max_chars"] == 1500
    assert cfg["min_chars"] == 100
    assert cfg["overlap_chars"] == 150


@pytest.mark.asyncio
async def test_upsert_inserts_when_absent(migrated: asyncpg.Pool) -> None:
    async with migrated.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_upsert_new")
    cfg = await upsert_chunking_config(
        migrated,
        workspace_id=ws_id,
        strategy="paragraph",
        max_chars=800, min_chars=80, overlap_chars=80,
        extras={},
    )
    assert cfg["max_chars"] == 800


@pytest.mark.asyncio
async def test_upsert_updates_updated_at(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    cfg_before = await get_chunking_config(workspace_id, migrated)
    import asyncio
    await asyncio.sleep(0.05)
    cfg_after = await upsert_chunking_config(
        migrated,
        workspace_id=workspace_id,
        strategy="paragraph",
        max_chars=1234, min_chars=100, overlap_chars=100,
        extras={},
    )
    assert cfg_after["updated_at"] > cfg_before["updated_at"]


@pytest.mark.asyncio
async def test_fk_cascade_on_workspace_delete(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    async with migrated.acquire() as conn:
        await conn.execute("DELETE FROM workspaces WHERE id = $1", workspace_id)
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM chunking_configs WHERE workspace_id = $1",
            workspace_id,
        )
    assert count == 0
```

- [ ] **Step 2: Lancer les tests pour confirmer l'échec**

Lancer : `cd backend && uv run pytest tests/integration/test_services_chunking_configs.py -v`
Attendu : ÉCHEC `ModuleNotFoundError: No module named 'rag.services.chunking_configs'`.

- [ ] **Step 3: Écrire le service**

`backend/src/rag/services/chunking_configs.py` :

```python
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg
import structlog

log = structlog.get_logger(__name__)


class ChunkingConfigNotFound(LookupError):
    """Le workspace n'a pas de chunking_config (état incohérent — devrait toujours exister)."""

    def __init__(self, workspace_id: UUID | str) -> None:
        super().__init__(f"chunking_config not found for workspace {workspace_id}")
        self.workspace_id = workspace_id


async def get_chunking_config(
    workspace_id: UUID | str,
    config_pool: asyncpg.Pool,
) -> dict[str, Any]:
    """Retourne la chunking_config du workspace. Raise ChunkingConfigNotFound si absente."""
    row = await config_pool.fetchrow(
        """
        SELECT workspace_id, strategy, max_chars, min_chars, overlap_chars,
               extras, created_at, updated_at
        FROM chunking_configs
        WHERE workspace_id = $1
        """,
        workspace_id,
    )
    if row is None:
        raise ChunkingConfigNotFound(workspace_id)
    return dict(row)


async def upsert_chunking_config(
    config_pool: asyncpg.Pool,
    *,
    workspace_id: UUID | str,
    strategy: str,
    max_chars: int,
    min_chars: int,
    overlap_chars: int,
    extras: dict[str, Any],
) -> dict[str, Any]:
    """INSERT ... ON CONFLICT DO UPDATE. Set updated_at=now(). Retourne la row."""
    row = await config_pool.fetchrow(
        """
        INSERT INTO chunking_configs
            (workspace_id, strategy, max_chars, min_chars, overlap_chars, extras)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        ON CONFLICT (workspace_id) DO UPDATE
            SET strategy      = EXCLUDED.strategy,
                max_chars     = EXCLUDED.max_chars,
                min_chars     = EXCLUDED.min_chars,
                overlap_chars = EXCLUDED.overlap_chars,
                extras        = EXCLUDED.extras,
                updated_at    = now()
        RETURNING workspace_id, strategy, max_chars, min_chars, overlap_chars,
                  extras, created_at, updated_at
        """,
        workspace_id, strategy, max_chars, min_chars, overlap_chars,
        json.dumps(extras),
    )
    if row is None:
        raise RuntimeError("upsert_chunking_config: INSERT did not RETURN")
    log.info(
        "chunking_config.upserted",
        workspace_id=str(workspace_id),
        strategy=strategy,
    )
    return dict(row)
```

Note : asyncpg renvoie `extras` comme un `str` JSON puisqu'on a fait `$6::jsonb`. Il faut vérifier — selon la configuration codec asyncpg, ça peut renvoyer un dict directement. Si le test `assert cfg["extras"] == {}` échoue, ajouter `json.loads` dans le mapping :

```python
out = dict(row)
if isinstance(out["extras"], str):
    out["extras"] = json.loads(out["extras"])
return out
```

Appliquer cette défense à `get_chunking_config` ET `upsert_chunking_config`.

- [ ] **Step 4: Lancer les tests pour confirmer le passage**

Lancer : `cd backend && uv run pytest tests/integration/test_services_chunking_configs.py -v`
Attendu : 6 tests PASS.

- [ ] **Step 5: Lint + format**

```bash
cd backend && uv run ruff check src/ tests/ && uv run ruff format src/ tests/ --check
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/rag/services/chunking_configs.py backend/tests/integration/test_services_chunking_configs.py
git commit -m "feat(M9-T5): service chunking_configs (get/upsert) + tests"
```

---

## Task 6 — Hook `create_workspace` (default + apply_pending) & `RealIndexer` + `upsert_chunks`

Cette tâche regroupe les modifs d'indexation : sans elles, les tests d'intégration de M4 cassent (cf. Task 3 step 9).

**Files:**
- Modify: `backend/src/rag/services/workspaces.py`
- Modify: `backend/src/rag/indexer/real.py`
- Modify: `backend/src/rag/db/workspace_embeddings.py`
- Create: `backend/tests/integration/test_create_workspace_with_chunking.py`
- Create: `backend/tests/integration/test_indexer_real_with_chunking_config.py`
- Modify: `backend/tests/integration/test_indexer_real.py` (adapter fixtures)

- [ ] **Step 1: Écrire le test `create_workspace` (rouge)**

`backend/tests/integration/test_create_workspace_with_chunking.py` :

```python
from __future__ import annotations

import asyncpg
import pytest

from rag.services.chunking_configs import get_chunking_config
from rag.services.workspaces import create_workspace
from rag.schemas.admin import IndexerSpec, WorkspaceCreateRequest


@pytest.mark.asyncio
async def test_create_workspace_inserts_default_chunking_config(
    migrated: asyncpg.Pool, admin_dsn: str,
) -> None:
    req = WorkspaceCreateRequest(
        name="ws_create_chunk",
        indexer=IndexerSpec(
            provider="ollama", model="mxbai-embed-large",
            api_key_ref=None, base_url="http://stub:11434",
        ),
    )
    try:
        ws = await create_workspace(
            req, config_pool=migrated, admin_dsn=admin_dsn,
            resolver=None, default_vault_name=None,
        )
        cfg = await get_chunking_config(ws["id"], migrated)
        assert cfg["strategy"] == "paragraph"
        assert cfg["max_chars"] == 2000
        assert cfg["min_chars"] == 200
        assert cfg["overlap_chars"] == 200
        assert cfg["extras"] == {}
    finally:
        from rag.db.workspace_schema import drop_workspace_database
        async with migrated.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT rag_base FROM workspaces WHERE name = 'ws_create_chunk'"
            )
            if row:
                await drop_workspace_database(admin_dsn, row["rag_base"])
            await conn.execute("DELETE FROM workspaces WHERE name = 'ws_create_chunk'")


@pytest.mark.asyncio
async def test_create_workspace_applies_workspace_migrations(
    migrated: asyncpg.Pool, admin_dsn: str,
) -> None:
    req = WorkspaceCreateRequest(
        name="ws_create_meta",
        indexer=IndexerSpec(
            provider="ollama", model="mxbai-embed-large",
            api_key_ref=None, base_url="http://stub:11434",
        ),
    )
    try:
        ws = await create_workspace(
            req, config_pool=migrated, admin_dsn=admin_dsn,
            resolver=None, default_vault_name=None,
        )

        from rag.db.workspace_schema import derive_workspace_dsn
        ws_dsn = derive_workspace_dsn(admin_dsn, ws["rag_base"])
        conn = await asyncpg.connect(ws_dsn)
        try:
            cols = {
                r["column_name"]
                for r in await conn.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'embeddings'"
                )
            }
            assert "metadata" in cols
            version = await conn.fetchval(
                "SELECT MAX(version) FROM workspace_schema_migrations"
            )
            assert version == 1
        finally:
            await conn.close()
    finally:
        from rag.db.workspace_schema import drop_workspace_database
        async with migrated.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT rag_base FROM workspaces WHERE name = 'ws_create_meta'"
            )
            if row:
                await drop_workspace_database(admin_dsn, row["rag_base"])
            await conn.execute("DELETE FROM workspaces WHERE name = 'ws_create_meta'")
```

Note : la signature exacte de `create_workspace` doit être vérifiée dans `backend/src/rag/services/workspaces.py`. Si elle diffère (par exemple resolver toujours requis), adapter le test.

- [ ] **Step 2: Écrire le test RealIndexer (rouge)**

`backend/tests/integration/test_indexer_real_with_chunking_config.py` :

```python
from __future__ import annotations

import asyncpg
import pytest

from rag.indexer.real import RealIndexer


@pytest.mark.asyncio
async def test_real_indexer_respects_chunking_config_max_chars(
    migrated: asyncpg.Pool, admin_dsn: str,
) -> None:
    """Le RealIndexer lit la chunking_config et applique max_chars."""
    # Préparation : workspace avec max_chars=500 → un texte de 1500 chars produit ≥ 2 chunks.
    from rag.services.workspaces import create_workspace
    from rag.schemas.admin import IndexerSpec, WorkspaceCreateRequest

    req = WorkspaceCreateRequest(
        name="ws_realidx_chunk",
        indexer=IndexerSpec(
            provider="ollama", model="mxbai-embed-large",
            api_key_ref=None, base_url="http://stub:11434",
        ),
    )
    ws = await create_workspace(
        req, config_pool=migrated, admin_dsn=admin_dsn,
        resolver=None, default_vault_name=None,
    )
    try:
        await migrated.execute(
            "UPDATE chunking_configs SET max_chars=500, min_chars=50, overlap_chars=50 "
            "WHERE workspace_id = $1",
            ws["id"],
        )

        # Stub provider qui retourne des embeddings dummy
        class _StubProvider:
            async def embed_texts(self, texts: list[str]) -> list[list[float]]:
                return [[0.0] * 8 for _ in texts]

        class _StubClient:
            async def get_default_vault_name(self) -> str | None:
                return None

        from rag.db.pool import WorkspacePoolRegistry
        registry = WorkspacePoolRegistry(init_dimension=8)
        indexer = RealIndexer(
            config_pool=migrated,
            pool_registry=registry,
            secret_resolver=None,
            client_provider=_StubClient(),
            provider_factory=lambda **kw: _StubProvider(),
        )

        # Texte 1500 chars
        content = "Phrase courte. " * 100
        nb = await indexer.index_file(
            workspace_id=ws["id"], path="t.md",
            content=content, content_hash="sha256:x",
            indexer_used="ollama/mxbai-embed-large",
        )
        assert nb >= 2

        # Vérifier que metadata est bien '{}' dans la base workspace
        from rag.db.workspace_schema import derive_workspace_dsn
        ws_dsn = derive_workspace_dsn(admin_dsn, ws["rag_base"])
        conn = await asyncpg.connect(ws_dsn)
        try:
            rows = await conn.fetch(
                "SELECT chunk_index, metadata FROM embeddings WHERE path = 't.md' "
                "ORDER BY chunk_index"
            )
            for r in rows:
                assert r["metadata"] == "{}" or r["metadata"] == {}
        finally:
            await conn.close()
    finally:
        from rag.db.workspace_schema import drop_workspace_database
        await drop_workspace_database(admin_dsn, ws["rag_base"])
        await migrated.execute(
            "DELETE FROM workspaces WHERE id = $1", ws["id"],
        )
```

Note : `WorkspacePoolRegistry(init_dimension=8)` est un signature spécifique : vérifier la vraie signature dans `rag/db/pool.py` et adapter. Si elle prend juste `config_pool`, adapter.

- [ ] **Step 3: Lancer les tests pour confirmer l'échec**

Lancer : `cd backend && uv run pytest tests/integration/test_create_workspace_with_chunking.py tests/integration/test_indexer_real_with_chunking_config.py -v`
Attendu : ÉCHEC (le hook n'existe pas + RealIndexer utilise encore l'ancien API `chunk_text`).

- [ ] **Step 4: Modifier `services/workspaces.py:create_workspace`**

Dans `backend/src/rag/services/workspaces.py`, identifier la transaction de création (`async with config_pool.acquire() as conn: async with conn.transaction(): ...`) et **juste après l'INSERT workspaces + INSERT indexer_configs**, ajouter avant le commit :

```python
await conn.execute(
    """
    INSERT INTO chunking_configs
        (workspace_id, strategy, max_chars, min_chars, overlap_chars, extras)
    VALUES ($1, 'paragraph', 2000, 200, 200, '{}'::jsonb)
    """,
    workspace_id,
)
```

Puis, **après** l'appel à `create_embeddings_table(workspace_dsn, dimension=...)` (qui crée la base + table embeddings) :

```python
from rag.db.workspace_migrations import apply_pending
await apply_pending(workspace_dsn)
```

(En cas d'échec d'`apply_pending`, la compensation existante de `create_workspace` doit drop la base. Vérifier que l'exception est bien propagée et que le try/except englobe `apply_pending`.)

- [ ] **Step 5: Modifier `upsert_chunks` pour accepter `list[Chunk]`**

`backend/src/rag/db/workspace_embeddings.py` : remplacer la signature et le INSERT.

```python
from __future__ import annotations

import json

import asyncpg
import structlog
from pgvector.asyncpg import register_vector

from rag.indexer.chunking import Chunk

log = structlog.get_logger(__name__)


async def upsert_chunks(
    workspace_pool: asyncpg.Pool,
    *,
    path: str,
    chunks: list[Chunk],
    embeddings: list[list[float]],
) -> int:
    """Remplace tous les chunks d'un path par une nouvelle liste.

    Pattern DELETE WHERE path=$1 puis INSERT batch, dans une transaction unique.
    Insère `metadata` (jsonb) en plus de `content`.
    Pre-condition : `len(chunks) == len(embeddings)` — sinon ValueError.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) must have "
            "the same length"
        )
    if not chunks:
        await delete_chunks_for_path(workspace_pool, path)
        return 0

    async with workspace_pool.acquire() as conn, conn.transaction():
        await register_vector(conn)
        await conn.execute("DELETE FROM embeddings WHERE path=$1", path)
        records = [
            (path, idx, chunk.content, embedding, json.dumps(chunk.metadata))
            for idx, (chunk, embedding) in enumerate(
                zip(chunks, embeddings, strict=True),
            )
        ]
        await conn.executemany(
            "INSERT INTO embeddings (path, chunk_index, content, embedding, metadata) "
            "VALUES ($1, $2, $3, $4, $5::jsonb)",
            records,
        )

    log.info("workspace_embeddings.upserted", path=path, chunks=len(chunks))
    return len(chunks)


async def delete_chunks_for_path(
    workspace_pool: asyncpg.Pool, path: str,
) -> int:
    """DELETE FROM embeddings WHERE path=$1. Retourne nombre supprimé."""
    async with workspace_pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM embeddings WHERE path=$1", path,
        )
    count = int(result.split()[-1])
    if count > 0:
        log.info("workspace_embeddings.deleted", path=path, count=count)
    return count


async def delete_path(workspace_pool: asyncpg.Pool, path: str) -> None:
    """Alias sémantique utilisé par RealIndexer."""
    await delete_chunks_for_path(workspace_pool, path)
```

- [ ] **Step 6: Modifier `RealIndexer`**

`backend/src/rag/indexer/real.py` :

```python
# Remplacer l'import en haut :
from rag.indexer.chunking import Chunk, make_chunker
# (supprimer `from rag.indexer.chunking import chunk_text`)
```

Dans `_load_workspace_context` : élargir le SELECT pour inclure les colonnes chunking :

```python
row = await self._config_pool.fetchrow(
    """
    SELECT
        w.name AS workspace_name,
        w.rag_cnx AS rag_cnx,
        ic.provider AS provider,
        ic.model AS model,
        ic.api_key_ref AS api_key_ref,
        ic.base_url AS base_url,
        cc.strategy AS chunking_strategy,
        cc.max_chars AS chunking_max_chars,
        cc.min_chars AS chunking_min_chars,
        cc.overlap_chars AS chunking_overlap_chars,
        cc.extras AS chunking_extras
    FROM workspaces w
    JOIN indexer_configs ic ON ic.workspace_id = w.id
    JOIN chunking_configs cc ON cc.workspace_id = w.id
    WHERE w.id = $1
    """,
    workspace_id,
)
if row is None:
    raise RuntimeError(
        f"Workspace {workspace_id} or its indexer/chunking config not found"
    )
ctx = dict(row)
# extras peut revenir en str selon codec asyncpg
if isinstance(ctx["chunking_extras"], str):
    import json
    ctx["chunking_extras"] = json.loads(ctx["chunking_extras"])
return ctx
```

Dans `index_file`, remplacer le bloc chunking :

```python
chunker = make_chunker(
    strategy=ctx["chunking_strategy"],
    max_chars=ctx["chunking_max_chars"],
    min_chars=ctx["chunking_min_chars"],
    overlap_chars=ctx["chunking_overlap_chars"],
    extras=ctx["chunking_extras"],
)
chunks: list[Chunk] = chunker.chunk(content)
if not chunks:
    log.info("real_indexer.empty_content_skipped", path=path)
    return 0
```

Et l'appel embed :

```python
embeddings = await provider.embed_texts([c.content for c in chunks])
```

Et l'appel upsert (la signature accepte `list[Chunk]` désormais) :

```python
await upsert_chunks(
    ws_pool,
    path=path,
    chunks=chunks,
    embeddings=embeddings,
)
```

- [ ] **Step 7: Adapter `test_indexer_real.py`**

Lancer : `grep -n "chunk_text\|chunking_configs" backend/tests/integration/test_indexer_real.py` pour repérer les imports/fixtures à mettre à jour.

Pour chaque test qui crée un workspace par seed direct (sans passer par `create_workspace`), ajouter l'INSERT default `chunking_configs` :

```python
await conn.execute(
    "INSERT INTO chunking_configs "
    "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
    "VALUES ($1, 'paragraph', 2000, 200, 200) ON CONFLICT DO NOTHING",
    ws_id,
)
```

Si les tests existants utilisaient des fixtures `create_workspace` réelles, aucune modif nécessaire (le hook s'en charge).

- [ ] **Step 8: Lancer tous les tests indexer**

Lancer : `cd backend && uv run pytest tests/integration/test_indexer_real.py tests/integration/test_indexer_real_with_chunking_config.py tests/integration/test_create_workspace_with_chunking.py -v`
Attendu : tous tests PASS.

- [ ] **Step 9: Smoke général**

Lancer : `cd backend && uv run pytest -x -q`
Attendu : toutes les suites passent. Si un test casse à cause d'un seed direct, corriger comme step 7.

- [ ] **Step 10: Lint + format**

```bash
cd backend && uv run ruff check src/ tests/ && uv run ruff format src/ tests/ --check
```

- [ ] **Step 11: Commit**

```bash
git add backend/src/rag/services/workspaces.py backend/src/rag/indexer/real.py backend/src/rag/db/workspace_embeddings.py backend/tests/integration/test_create_workspace_with_chunking.py backend/tests/integration/test_indexer_real_with_chunking_config.py backend/tests/integration/test_indexer_real.py
git commit -m "feat(M9-T6): RealIndexer lit chunking_config + upsert_chunks gere metadata + hook create_workspace"
```

---

## Task 7 — Migration 013 + `apply_chunking_change` + erreur `ChunkingChangeRequiresReindex`

**Files:**
- Create: `backend/migrations/013_index_jobs_chunking_change_trigger.sql`
- Modify: `backend/src/rag/api/errors.py`
- Modify: `backend/src/rag/services/jobs.py`
- Create: `backend/tests/integration/test_migration_013_chunking_trigger.py`
- Modify: `backend/tests/integration/test_services_chunking_configs.py` (ou nouveau fichier pour apply_chunking_change)

- [ ] **Step 1: Test migration 013 (rouge)**

`backend/tests/integration/test_migration_013_chunking_trigger.py` :

```python
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_triggered_by_accepts_reindex_chunking_change(
    session_pool: asyncpg.Pool,
) -> None:
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS chunking_configs, rerank_configs, indexer_configs, "
            "workspace_sources, index_jobs, indexed_documents, "
            "workspaces, harpocrate_vaults, model_dimensions, "
            "schema_migrations CASCADE"
        )
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_chunk_trig")
        await conn.execute(
            "INSERT INTO index_jobs (workspace_id, triggered_by) VALUES ($1, $2)",
            ws_id, "reindex_chunking_change",
        )
        rows = await conn.fetch(
            "SELECT triggered_by FROM index_jobs WHERE workspace_id = $1", ws_id,
        )
    assert rows[0]["triggered_by"] == "reindex_chunking_change"


@pytest.mark.asyncio
async def test_triggered_by_rejects_unknown(session_pool: asyncpg.Pool) -> None:
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS chunking_configs, rerank_configs, indexer_configs, "
            "workspace_sources, index_jobs, indexed_documents, "
            "workspaces, harpocrate_vaults, model_dimensions, "
            "schema_migrations CASCADE"
        )
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_chunk_trig_bad")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO index_jobs (workspace_id, triggered_by) VALUES ($1, $2)",
                ws_id, "nope",
            )
```

- [ ] **Step 2: Lancer le test (rouge)**

Lancer : `cd backend && uv run pytest tests/integration/test_migration_013_chunking_trigger.py -v`
Attendu : ÉCHEC (`reindex_chunking_change` violates CHECK).

- [ ] **Step 3: Écrire la migration 013**

Lancer : `cat backend/migrations/007_index_jobs_reindex_trigger.sql` pour récupérer la liste actuelle des valeurs autorisées.

Puis créer `backend/migrations/013_index_jobs_chunking_change_trigger.sql` :

```sql
-- Migration 013 — élargit le CHECK index_jobs.triggered_by avec 'reindex_chunking_change'
--
-- Symétrique à 007 (qui a ajouté 'reindex_indexer_change' lors de M5).
-- Permet aux jobs créés par apply_chunking_change(confirm=true) de s'insérer.

ALTER TABLE index_jobs DROP CONSTRAINT index_jobs_triggered_by_check;
ALTER TABLE index_jobs ADD CONSTRAINT index_jobs_triggered_by_check
    CHECK (triggered_by IN (
        'manual',
        'webhook',
        'push',
        'schedule',
        'reindex_indexer_change',
        'reindex_chunking_change'
    ));
```

Note : si la liste exacte des valeurs autorisées dans 007 diffère (par exemple absence de `'push'`), aligner sur ce qui est réellement présent en base, en ajoutant uniquement `'reindex_chunking_change'`.

- [ ] **Step 4: Lancer les tests (vert)**

Lancer : `cd backend && uv run pytest tests/integration/test_migration_013_chunking_trigger.py -v`
Attendu : 2 tests PASS.

- [ ] **Step 5: Ajouter `ChunkingChangeRequiresReindex` dans errors.py (test rouge)**

`backend/tests/api/test_chunking_change_error.py` (nouveau, court) :

```python
from __future__ import annotations

import pytest

from rag.api.errors import ChunkingChangeRequiresReindex


def test_error_payload_format() -> None:
    err = ChunkingChangeRequiresReindex(
        workspace="ws_x",
        current="paragraph (max=2000, min=200, overlap=200)",
        new="paragraph (max=1500, min=100, overlap=150)",
    )
    payload = err.to_payload()
    assert payload["error"] == "chunking_change_requires_reindex"
    assert payload["workspace"] == "ws_x"
    assert payload["current"] == "paragraph (max=2000, min=200, overlap=200)"
    assert payload["new"] == "paragraph (max=1500, min=100, overlap=150)"
    assert payload["action"] == "PUT /workspaces/ws_x/chunking-config?confirm=true"
```

Note : adapter la forme `.to_payload()` au pattern existant dans `errors.py`. Vérifier `cat backend/src/rag/api/errors.py | head -120`.

- [ ] **Step 6: Lancer (rouge)**

Lancer : `cd backend && uv run pytest tests/api/test_chunking_change_error.py -v`
Attendu : ÉCHEC `ImportError`.

- [ ] **Step 7: Ajouter la classe d'erreur**

Dans `backend/src/rag/api/errors.py`, sur le modèle de `IndexerChangeRequiresReindex` (consulter le code existant pour aligner le format exact). Ajouter :

```python
class ChunkingChangeRequiresReindex(Exception):
    """Lever quand l'utilisateur tente de modifier chunking_config alors
    que des documents sont indexés et qu'il n'a pas confirmé."""

    def __init__(self, *, workspace: str, current: str, new: str) -> None:
        super().__init__(
            f"chunking config change for workspace {workspace!r} requires reindex "
            f"(current={current}, new={new})"
        )
        self.workspace = workspace
        self.current = current
        self.new = new

    def to_payload(self) -> dict[str, str]:
        return {
            "error": "chunking_change_requires_reindex",
            "workspace": self.workspace,
            "current": self.current,
            "new": self.new,
            "action": (
                f"PUT /workspaces/{self.workspace}/chunking-config?confirm=true"
            ),
        }
```

- [ ] **Step 8: Lancer (vert)**

Lancer : `cd backend && uv run pytest tests/api/test_chunking_change_error.py -v`
Attendu : PASS.

- [ ] **Step 9: Écrire les tests `apply_chunking_change` (rouge)**

Ajouter dans `backend/tests/integration/test_services_chunking_configs.py` :

```python
@pytest.mark.asyncio
async def test_apply_chunking_change_no_change_returns_no_change(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    from rag.schemas.admin import ChunkingConfigSpec
    from rag.services.jobs import apply_chunking_change

    spec = ChunkingConfigSpec(
        strategy="paragraph", max_chars=2000, min_chars=200,
        overlap_chars=200, extras={},
    )
    result = await apply_chunking_change(
        name="ws_chunking_svc", payload=spec, confirm=False, config_pool=migrated,
    )
    assert result == "no_change"


@pytest.mark.asyncio
async def test_apply_chunking_change_no_docs_updates(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    from rag.schemas.admin import ChunkingConfigSpec
    from rag.services.jobs import apply_chunking_change

    spec = ChunkingConfigSpec(
        strategy="paragraph", max_chars=1500, min_chars=100,
        overlap_chars=150, extras={},
    )
    result = await apply_chunking_change(
        name="ws_chunking_svc", payload=spec, confirm=False, config_pool=migrated,
    )
    assert isinstance(result, tuple)
    tag, new_cfg = result
    assert tag == "updated"
    assert new_cfg["max_chars"] == 1500


@pytest.mark.asyncio
async def test_apply_chunking_change_with_docs_raises_without_confirm(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    from rag.api.errors import ChunkingChangeRequiresReindex
    from rag.schemas.admin import ChunkingConfigSpec
    from rag.services.jobs import apply_chunking_change

    # Seed 1 indexed_document pour le workspace
    await migrated.execute(
        "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
        "VALUES ($1, $2, $3, $4)",
        workspace_id, "a.md", "sha256:0", "ollama/x",
    )

    spec = ChunkingConfigSpec(
        strategy="paragraph", max_chars=1500, min_chars=100,
        overlap_chars=150, extras={},
    )
    with pytest.raises(ChunkingChangeRequiresReindex):
        await apply_chunking_change(
            name="ws_chunking_svc", payload=spec, confirm=False,
            config_pool=migrated,
        )


@pytest.mark.asyncio
async def test_apply_chunking_change_with_docs_and_confirm_triggers_reindex(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    from rag.schemas.admin import ChunkingConfigSpec
    from rag.services.jobs import apply_chunking_change

    await migrated.execute(
        "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
        "VALUES ($1, $2, $3, $4)",
        workspace_id, "b.md", "sha256:0", "ollama/x",
    )

    spec = ChunkingConfigSpec(
        strategy="paragraph", max_chars=1500, min_chars=100,
        overlap_chars=150, extras={},
    )
    result = await apply_chunking_change(
        name="ws_chunking_svc", payload=spec, confirm=True, config_pool=migrated,
    )
    assert isinstance(result, tuple)
    tag, job_row = result
    assert tag == "reindex_triggered"
    assert job_row["triggered_by"] == "reindex_chunking_change"
    assert job_row["status"] == "pending"

    # La config est bien mise à jour
    new_cfg = await migrated.fetchrow(
        "SELECT max_chars FROM chunking_configs WHERE workspace_id = $1",
        workspace_id,
    )
    assert new_cfg["max_chars"] == 1500
```

- [ ] **Step 10: Lancer (rouge)**

Lancer : `cd backend && uv run pytest tests/integration/test_services_chunking_configs.py -v`
Attendu : 4 nouveaux tests ÉCHOUENT (`ImportError: apply_chunking_change`).

- [ ] **Step 11: Implémenter `apply_chunking_change`**

Ajouter à `backend/src/rag/services/jobs.py` (en regardant d'abord `apply_indexer_change` / `reindex_workspace` pour le pattern) :

```python
from typing import Literal

from rag.api.errors import ChunkingChangeRequiresReindex
from rag.schemas.admin import ChunkingConfigSpec
from rag.services.chunking_configs import (
    get_chunking_config,
    upsert_chunking_config,
)


ApplyChunkingResult = (
    Literal["no_change"]
    | tuple[Literal["updated"], dict[str, Any]]
    | tuple[Literal["reindex_triggered"], dict[str, Any]]
)


def _format_chunking_desc(cfg: dict[str, Any]) -> str:
    return (
        f"{cfg['strategy']} "
        f"(max={cfg['max_chars']}, min={cfg['min_chars']}, "
        f"overlap={cfg['overlap_chars']})"
    )


def _payload_matches(payload: ChunkingConfigSpec, current: dict[str, Any]) -> bool:
    return (
        payload.strategy == current["strategy"]
        and payload.max_chars == current["max_chars"]
        and payload.min_chars == current["min_chars"]
        and payload.overlap_chars == current["overlap_chars"]
        and payload.extras == current["extras"]
    )


async def apply_chunking_change(
    *,
    name: str,
    payload: ChunkingConfigSpec,
    confirm: bool,
    config_pool: asyncpg.Pool,
) -> ApplyChunkingResult:
    """Applique un changement de chunking_config sur un workspace.

    - Si payload identique à la config actuelle → 'no_change' (caller renvoie 204).
    - Sinon, compte indexed_documents :
      * 0 doc → upsert + ('updated', new_cfg) (caller renvoie 200).
      * >0 doc + !confirm → raise ChunkingChangeRequiresReindex (caller renvoie 409).
      * >0 doc + confirm → upsert + create_pending_job en une transaction +
        ('reindex_triggered', job_row) (caller renvoie 202).
    """
    ws_row = await config_pool.fetchrow(
        "SELECT id FROM workspaces WHERE name = $1", name,
    )
    if ws_row is None:
        raise LookupError(f"workspace {name!r} not found")
    workspace_id = ws_row["id"]

    current = await get_chunking_config(workspace_id, config_pool)
    if _payload_matches(payload, current):
        return "no_change"

    docs = await config_pool.fetchval(
        "SELECT COUNT(*) FROM indexed_documents WHERE workspace_id = $1",
        workspace_id,
    )

    if docs == 0:
        new_cfg = await upsert_chunking_config(
            config_pool,
            workspace_id=workspace_id,
            strategy=payload.strategy,
            max_chars=payload.max_chars,
            min_chars=payload.min_chars,
            overlap_chars=payload.overlap_chars,
            extras=payload.extras,
        )
        return ("updated", new_cfg)

    if not confirm:
        raise ChunkingChangeRequiresReindex(
            workspace=name,
            current=_format_chunking_desc(current),
            new=_format_chunking_desc({
                "strategy": payload.strategy,
                "max_chars": payload.max_chars,
                "min_chars": payload.min_chars,
                "overlap_chars": payload.overlap_chars,
            }),
        )

    async with config_pool.acquire() as conn, conn.transaction():
        await conn.execute(
            """
            INSERT INTO chunking_configs
                (workspace_id, strategy, max_chars, min_chars, overlap_chars, extras)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            ON CONFLICT (workspace_id) DO UPDATE
                SET strategy=EXCLUDED.strategy,
                    max_chars=EXCLUDED.max_chars,
                    min_chars=EXCLUDED.min_chars,
                    overlap_chars=EXCLUDED.overlap_chars,
                    extras=EXCLUDED.extras,
                    updated_at=now()
            """,
            workspace_id, payload.strategy, payload.max_chars,
            payload.min_chars, payload.overlap_chars,
            json.dumps(payload.extras),
        )
        job_row = await conn.fetchrow(
            """
            INSERT INTO index_jobs (workspace_id, triggered_by, status)
            VALUES ($1, 'reindex_chunking_change', 'pending')
            RETURNING id, workspace_id, source_id, triggered_by, status,
                      files_changed, files_skipped, error_message,
                      started_at, finished_at, duration_ms
            """,
            workspace_id,
        )

    return ("reindex_triggered", dict(job_row))
```

Importer `json` en tête si nécessaire.

- [ ] **Step 12: Lancer les tests (vert)**

Lancer : `cd backend && uv run pytest tests/integration/test_services_chunking_configs.py tests/api/test_chunking_change_error.py -v`
Attendu : tous tests PASS.

- [ ] **Step 13: Lint + format**

```bash
cd backend && uv run ruff check src/ tests/ && uv run ruff format src/ tests/ --check
```

- [ ] **Step 14: Commit**

```bash
git add backend/migrations/013_index_jobs_chunking_change_trigger.sql backend/src/rag/api/errors.py backend/src/rag/services/jobs.py backend/tests/integration/test_migration_013_chunking_trigger.py backend/tests/api/test_chunking_change_error.py backend/tests/integration/test_services_chunking_configs.py
git commit -m "feat(M9-T7): apply_chunking_change + ChunkingChangeRequiresReindex + migration 013"
```

---

## Task 8 — Endpoints API admin `GET/PUT /chunking-config`

**Files:**
- Modify: `backend/src/rag/api/admin.py`
- Create: `backend/tests/api/test_admin_workspaces_chunking.py`

- [ ] **Step 1: Tests d'API (rouge)**

`backend/tests/api/test_admin_workspaces_chunking.py` :

```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _create_ws(client: TestClient, name: str) -> str:
    r = client.post(
        "/api/admin/workspaces",
        json={
            "name": name,
            "indexer": {
                "provider": "ollama", "model": "mxbai-embed-large",
                "api_key_ref": None, "base_url": "http://stub:11434",
            },
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_get_chunking_config_returns_default(client: TestClient) -> None:
    name = "api_chunk_get"
    _create_ws(client, name)
    r = client.get(f"/api/admin/workspaces/{name}/chunking-config")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["strategy"] == "paragraph"
    assert body["max_chars"] == 2000
    assert body["min_chars"] == 200
    assert body["overlap_chars"] == 200
    assert body["extras"] == {}


@pytest.mark.asyncio
async def test_get_chunking_config_404_unknown_workspace(client: TestClient) -> None:
    r = client.get("/api/admin/workspaces/nope/chunking-config")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_put_chunking_config_identical_returns_204(client: TestClient) -> None:
    name = "api_chunk_id"
    _create_ws(client, name)
    r = client.put(
        f"/api/admin/workspaces/{name}/chunking-config",
        json={
            "strategy": "paragraph", "max_chars": 2000, "min_chars": 200,
            "overlap_chars": 200, "extras": {},
        },
    )
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_put_chunking_config_no_docs_returns_200(client: TestClient) -> None:
    name = "api_chunk_chg"
    _create_ws(client, name)
    r = client.put(
        f"/api/admin/workspaces/{name}/chunking-config",
        json={
            "strategy": "paragraph", "max_chars": 1500, "min_chars": 100,
            "overlap_chars": 150, "extras": {},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["max_chars"] == 1500


@pytest.mark.asyncio
async def test_put_chunking_config_with_docs_no_confirm_returns_409(
    client: TestClient, migrated,
) -> None:
    name = "api_chunk_409"
    ws_id = _create_ws(client, name)
    # Force 1 indexed_document directement en DB pour le test
    await migrated.execute(
        "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
        "VALUES ($1, 'x.md', 'sha256:0', 'ollama/m')",
        ws_id,
    )
    r = client.put(
        f"/api/admin/workspaces/{name}/chunking-config",
        json={
            "strategy": "paragraph", "max_chars": 1500, "min_chars": 100,
            "overlap_chars": 150, "extras": {},
        },
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "chunking_change_requires_reindex"
    assert body["action"] == f"PUT /workspaces/{name}/chunking-config?confirm=true"


@pytest.mark.asyncio
async def test_put_chunking_config_with_docs_and_confirm_returns_202(
    client: TestClient, migrated,
) -> None:
    name = "api_chunk_202"
    ws_id = _create_ws(client, name)
    await migrated.execute(
        "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
        "VALUES ($1, 'y.md', 'sha256:0', 'ollama/m')",
        ws_id,
    )
    r = client.put(
        f"/api/admin/workspaces/{name}/chunking-config?confirm=true",
        json={
            "strategy": "paragraph", "max_chars": 1500, "min_chars": 100,
            "overlap_chars": 150, "extras": {},
        },
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["triggered_by"] == "reindex_chunking_change"
    assert body["status"] == "pending"


@pytest.mark.asyncio
async def test_put_chunking_config_invalid_payload_returns_422(
    client: TestClient,
) -> None:
    name = "api_chunk_422"
    _create_ws(client, name)
    r = client.put(
        f"/api/admin/workspaces/{name}/chunking-config",
        json={
            "strategy": "paragraph", "max_chars": 100, "min_chars": 200,
            "overlap_chars": 50, "extras": {},
        },
    )
    assert r.status_code == 422
```

- [ ] **Step 2: Lancer (rouge)**

Lancer : `cd backend && uv run pytest tests/api/test_admin_workspaces_chunking.py -v`
Attendu : ÉCHEC `404 not found` ou équivalent (endpoints absents).

- [ ] **Step 3: Ajouter les endpoints**

Dans `backend/src/rag/api/admin.py`, après les endpoints rerank, ajouter (en se calquant sur `get_rerank_config` / `put_rerank_config`) :

```python
# ─── Chunking config ────────────────────────────────────────────────────

@router.get("/workspaces/{name}/chunking-config")
async def get_chunking_config_endpoint(
    name: str, request: Request,
) -> ChunkingConfigResponse:
    from rag.services.chunking_configs import (
        ChunkingConfigNotFound, get_chunking_config,
    )

    config_pool = _config_pool(request)
    ws_row = await config_pool.fetchrow(
        "SELECT id FROM workspaces WHERE name = $1", name,
    )
    if ws_row is None:
        raise HTTPException(status_code=404, detail=f"workspace {name!r} not found")
    try:
        cfg = await get_chunking_config(ws_row["id"], config_pool)
    except ChunkingConfigNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ChunkingConfigResponse(**cfg)


@router.put("/workspaces/{name}/chunking-config")
async def put_chunking_config_endpoint(
    name: str,
    payload: ChunkingConfigSpec,
    request: Request,
    confirm: bool = False,
) -> Response:
    from rag.api.errors import ChunkingChangeRequiresReindex
    from rag.services.jobs import apply_chunking_change

    config_pool = _config_pool(request)
    try:
        result = await apply_chunking_change(
            name=name, payload=payload, confirm=confirm, config_pool=config_pool,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ChunkingChangeRequiresReindex as exc:
        raise HTTPException(status_code=409, detail=exc.to_payload()) from exc

    if result == "no_change":
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    tag, body = result
    if tag == "updated":
        return JSONResponse(
            status_code=200,
            content=ChunkingConfigResponse(**body).model_dump(mode="json"),
        )
    # tag == "reindex_triggered"
    return JSONResponse(
        status_code=202,
        content=JobResponse(**body).model_dump(mode="json"),
    )
```

Vérifier les imports requis en tête du fichier (`ChunkingConfigResponse`, `ChunkingConfigSpec`, éventuellement `JSONResponse`).

- [ ] **Step 4: Lancer (vert)**

Lancer : `cd backend && uv run pytest tests/api/test_admin_workspaces_chunking.py -v`
Attendu : 7 tests PASS.

- [ ] **Step 5: Lint + format**

```bash
cd backend && uv run ruff check src/ tests/ && uv run ruff format src/ tests/ --check
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/rag/api/admin.py backend/tests/api/test_admin_workspaces_chunking.py
git commit -m "feat(M9-T8): endpoints GET/PUT /workspaces/{name}/chunking-config"
```

---

## Task 9 — Boot scan lifespan (apply_pending sur chaque workspace au startup)

**Files:**
- Modify: `backend/src/agflow/main.py` (ou module hébergeant le lifespan)
- Create: `backend/tests/integration/test_boot_workspace_migrations.py`

- [ ] **Step 1: Localiser le lifespan**

Lancer : `grep -rn "lifespan\|FastAPI(" backend/src/agflow/ backend/src/rag/ | head -10`
Vérifier où est défini le lifespan et adapter le path du fichier modifié si nécessaire (probablement `backend/src/agflow/main.py` mais à confirmer).

- [ ] **Step 2: Tests boot scan (rouge)**

`backend/tests/integration/test_boot_workspace_migrations.py` :

```python
from __future__ import annotations

import asyncpg
import pytest

from rag.db.workspace_migrations import apply_pending
from rag.db.workspace_schema import derive_workspace_dsn


async def _create_legacy_db(admin_dsn: str, name: str) -> None:
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()
    dsn = derive_workspace_dsn(admin_dsn, name)
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(
            "CREATE TABLE embeddings ("
            "id SERIAL PRIMARY KEY, path TEXT NOT NULL, chunk_index INT NOT NULL, "
            "content TEXT NOT NULL, embedding vector(8) NOT NULL, "
            "indexed_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_boot_scan_applies_migrations_to_all_workspaces(
    admin_dsn: str, migrated: asyncpg.Pool,
) -> None:
    # Crée 2 workspaces 'anciens'
    base_a = "rag_boot_a"
    base_b = "rag_boot_b"
    await _create_legacy_db(admin_dsn, base_a)
    await _create_legacy_db(admin_dsn, base_b)

    from tests.integration._workspace_seed import seed_workspace
    async with migrated.acquire() as conn:
        await seed_workspace(
            conn, name="ws_boot_a", rag_cnx=derive_workspace_dsn(admin_dsn, base_a),
            rag_base=base_a,
        )
        await seed_workspace(
            conn, name="ws_boot_b", rag_cnx=derive_workspace_dsn(admin_dsn, base_b),
            rag_base=base_b,
        )

    try:
        # Simule le boot scan
        from rag.db.workspace_migrations.boot import apply_pending_for_all_workspaces
        await apply_pending_for_all_workspaces(migrated)

        # Vérifie : les 2 bases ont metadata + version 1
        for base in (base_a, base_b):
            dsn = derive_workspace_dsn(admin_dsn, base)
            conn = await asyncpg.connect(dsn)
            try:
                version = await conn.fetchval(
                    "SELECT MAX(version) FROM workspace_schema_migrations"
                )
                cols = {
                    r["column_name"]
                    for r in await conn.fetch(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'embeddings'"
                    )
                }
                assert version == 1
                assert "metadata" in cols
            finally:
                await conn.close()
    finally:
        admin = await asyncpg.connect(admin_dsn)
        try:
            for base in (base_a, base_b):
                await admin.execute(f'DROP DATABASE IF EXISTS "{base}" WITH (FORCE)')
        finally:
            await admin.close()


@pytest.mark.asyncio
async def test_boot_scan_fail_fast_on_unreachable_db(
    admin_dsn: str, migrated: asyncpg.Pool,
) -> None:
    from tests.integration._workspace_seed import seed_workspace
    async with migrated.acquire() as conn:
        await seed_workspace(
            conn, name="ws_boot_broken",
            rag_cnx="postgresql://nope:nope@127.0.0.1:1/nope",
            rag_base="nope",
        )

    from rag.db.workspace_migrations.boot import apply_pending_for_all_workspaces
    with pytest.raises(Exception):
        await apply_pending_for_all_workspaces(migrated)
```

- [ ] **Step 3: Lancer (rouge)**

Lancer : `cd backend && uv run pytest tests/integration/test_boot_workspace_migrations.py -v`
Attendu : ÉCHEC `ImportError: No module named 'rag.db.workspace_migrations.boot'`.

- [ ] **Step 4: Implémenter `apply_pending_for_all_workspaces`**

Ajouter `backend/src/rag/db/workspace_migrations/boot.py` :

```python
from __future__ import annotations

import asyncpg
import structlog

from rag.db.workspace_migrations.runner import apply_pending

log = structlog.get_logger(__name__)


async def apply_pending_for_all_workspaces(config_pool: asyncpg.Pool) -> None:
    """Itère sur tous les workspaces et applique leurs migrations workspace manquantes.

    Fail-fast : si une base est inaccessible ou une migration plante, raise. Le
    service refuse alors de démarrer.
    """
    rows = await config_pool.fetch("SELECT name, rag_cnx FROM workspaces ORDER BY name")
    for row in rows:
        name = row["name"]
        dsn = row["rag_cnx"]
        try:
            applied = await apply_pending(dsn)
            if applied:
                log.info("workspace_migration.applied",
                         workspace=name, count=applied)
        except Exception:
            log.error("workspace_migration.failed",
                      workspace=name, exc_info=True)
            raise
```

Et exposer dans `backend/src/rag/db/workspace_migrations/__init__.py` :

```python
from __future__ import annotations

from .boot import apply_pending_for_all_workspaces
from .runner import apply_pending

__all__ = ["apply_pending", "apply_pending_for_all_workspaces"]
```

- [ ] **Step 5: Brancher le boot scan dans le lifespan**

Dans le fichier de lifespan (à confirmer après step 1, probablement `backend/src/agflow/main.py`), après init `config_pool`, avant `yield` :

```python
from rag.db.workspace_migrations import apply_pending_for_all_workspaces

# ... à l'intérieur du lifespan startup, après config_pool prêt :
await apply_pending_for_all_workspaces(config_pool)
```

- [ ] **Step 6: Lancer (vert)**

Lancer : `cd backend && uv run pytest tests/integration/test_boot_workspace_migrations.py -v`
Attendu : 2 tests PASS.

- [ ] **Step 7: Lancer la suite complète backend**

Lancer : `cd backend && uv run pytest -x -q`
Attendu : tous les tests passent.

- [ ] **Step 8: Lint + format + typecheck**

```bash
cd backend && uv run ruff check src/ tests/ && uv run ruff format src/ tests/ --check
```

- [ ] **Step 9: Smoke démarrage app**

Lancer dans une fenêtre séparée : `cd backend && uv run uvicorn agflow.main:app --port 8000`
Attendu : démarrage sans erreur, logs `workspace_migration.applied` pour chaque workspace migré (ou rien si déjà migrés).

- [ ] **Step 10: Commit**

```bash
git add backend/src/rag/db/workspace_migrations/ backend/src/agflow/main.py backend/tests/integration/test_boot_workspace_migrations.py
git commit -m "feat(M9-T9): boot scan workspace_migrations (lifespan + fail-fast)"
```

---

## Task 10 — Roadmap & validation finale

**Files:**
- Modify: `specs/09-roadmap.md`

- [ ] **Step 1: Mettre à jour la roadmap**

Modifier `specs/09-roadmap.md` § « Amélioration du chunking » :

```markdown
### Amélioration du chunking

✅ Infrastructure livrée en M9 — cf. `docs/superpowers/specs/2026-05-18-M9-backend-chunking-infrastructure-design.md`.

Pattern factory + registry par stratégie, config par workspace (table `chunking_configs`), champ `embeddings.metadata jsonb` prêt, runner de migrations workspace au boot. Une seule stratégie disponible : `paragraph` (algo historique). Frontend dédié différé en M9b.

Stratégies futures (jalons distincts) :
- Chunking sémantique (respect des sections Markdown)
- Chunking par blocs de code
- Métadonnées de chunk enrichies (titre de section parent, type de contenu)
```

- [ ] **Step 2: Smoke final**

```bash
cd backend && uv run pytest -q && uv run ruff check src/ tests/
```

Attendu : tout vert.

- [ ] **Step 3: Commit roadmap**

```bash
git add specs/09-roadmap.md
git commit -m "docs(M9-T10): roadmap marque M9 livre (chunking infrastructure)"
```

---

## Self-review du plan (à exécuter avant handoff)

1. **Couverture spec** :
   - §2 Décisions D1-D14 → toutes implémentées (D1/D2 Task 1+5, D3 Task 1+4, D4 Task 1, D5 Task 2, D6/D7/D8 Task 2+9, D9/D10/D11 Task 3, D12/D13 Task 7+8, D14 = hors-scope)
   - §3 Schéma BDD → Tasks 1, 2, 7
   - §4 Composants → Tasks 3, 5, 6
   - §5 API REST → Task 8
   - §6 Boot scan → Task 9
   - §7 Tests → distribués sur chaque task

2. **Aucun placeholder** : tous les snippets sont complets. Quelques "vérifier d'abord X" ciblent des inspections rapides du code existant (signatures `create_workspace`, format exact `IndexerChangeRequiresReindex`, position lifespan) — légitimes car ces signatures dépendent du code actuel non visible en intégralité dans la spec.

3. **Cohérence types** :
   - `Chunk(content: str, metadata: dict)` : utilisé identiquement dans paragraph.py, factory.py, real.py, workspace_embeddings.py
   - `make_chunker(*, strategy, max_chars, min_chars, overlap_chars, extras)` : mêmes kwargs partout
   - `get_chunking_config(workspace_id, config_pool)` ordre des args cohérent entre service / test / endpoint
   - `apply_chunking_change(*, name, payload, confirm, config_pool)` cohérent
   - `ApplyChunkingResult` retour cohérent service / endpoint
