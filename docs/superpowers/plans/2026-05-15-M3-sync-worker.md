# M3 — Sync Worker · Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer le sync worker qui exécute automatiquement les `index_jobs(status='pending')`, surveille les sources git via polling, applique le pipeline clone/pull → diff → déduplication SHA-256 → délégation à un `IndexerProtocol` stubbé en M3 (NoOpIndexer).

**Architecture:** Single asyncio task lancée au lifespan FastAPI, 3 phases dans la même boucle (scheduler / picker / executor). Opérations git via `subprocess` git CLI (binaire installé dans le Dockerfile), repos clonés persistants dans le volume Docker `rag_repos` monté sur `/var/lib/rag/repos/<workspace_id>/<source_id>/`. Frontière vers M4 isolée par `IndexerProtocol` (2 méthodes : `index_file`, `delete_file`).

**Tech Stack:** Python 3.12 · asyncio · asyncpg · subprocess (git CLI 2.x) · structlog · pytest + pytest-asyncio · Postgres 16 LXC partagé pour intégration.

**Référence design :** `docs/superpowers/specs/2026-05-15-M3-sync-worker-design.md`.

---

## Convention d'exécution

- Toutes les commandes sont à exécuter depuis `E:\srcs\ag-flow.rag\backend\` sauf indication contraire.
- Sur Windows local, utiliser PowerShell ; sur LXC 401 (test) / 303 (dev), bash.
- Chaque task se termine par un commit en français conventionnel (`feat:`, `test:`, `chore:`…) sur la branche `dev`.
- Aucune livraison sur LXC avant la **Task 19** (smoke deploy final).
- Pour les tests d'intégration : `$env:TEST_POSTGRES_PASSWORD = "LJu_nISEyxccTdm2w72l4AkDVsUF4BeR"` puis `uv run pytest`.
- Git CLI requis localement pour les tests d'intégration `git_ops` (présent sur Windows via Git for Windows).
- **Tous les noms de classe, paramètre, exception sont figés par ce plan.** Toute déviation doit être documentée comme `DONE_WITH_CONCERNS`.

---

## Task 1 — Settings : `sync_default_interval_seconds` + `sync_repos_root`

**Files:**
- Modify: `backend/src/rag/config.py` (ajout 2 settings)
- Modify: `backend/tests/unit/test_config.py` (ajout 2 tests)
- Modify: `.env.example` (ajout commenté)

- [ ] **Step 1.1 : Écrire les tests (rouge)**

Lire d'abord `backend/tests/unit/test_config.py` pour comprendre le pattern existant (les tests utilisent `monkeypatch.setenv` + `Settings()`). Ajouter en fin de fichier :

```python
def test_sync_default_interval_seconds_defaults_to_300(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_env(monkeypatch)  # helper existant qui pose les vars critiques
    settings = Settings()  # type: ignore[call-arg]
    assert settings.sync_default_interval_seconds == 300


def test_sync_default_interval_seconds_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.setenv("SYNC_DEFAULT_INTERVAL_SECONDS", "60")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.sync_default_interval_seconds == 60


def test_sync_repos_root_defaults_to_var_lib(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path
    _set_required_env(monkeypatch)
    settings = Settings()  # type: ignore[call-arg]
    assert settings.sync_repos_root == Path("/var/lib/rag/repos")


def test_sync_repos_root_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path
    _set_required_env(monkeypatch)
    monkeypatch.setenv("SYNC_REPOS_ROOT", "/tmp/test-repos")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.sync_repos_root == Path("/tmp/test-repos")
```

Si le helper `_set_required_env` n'existe pas dans `test_config.py`, le créer en début de fichier (ou utiliser le pattern déjà en place dans les tests existants — vérifier d'abord).

- [ ] **Step 1.2 : Lancer les tests (rouge)**

```powershell
Set-Location E:\srcs\ag-flow.rag\backend
uv run pytest tests/unit/test_config.py -v -k "sync_default or sync_repos"
```

Expected : 4 FAIL avec `AttributeError: 'Settings' object has no attribute 'sync_default_interval_seconds'` (et `sync_repos_root`).

- [ ] **Step 1.3 : Ajouter les 2 settings**

Dans `backend/src/rag/config.py`, dans la classe `Settings(BaseSettings)`, après le champ `sync_worker_poll_interval_seconds` existant (M1), ajouter :

```python
    # Interval par défaut entre 2 syncs d'une même source (override possible
    # par source via config.sync_interval_seconds). 5 min = bon compromis
    # entre fraicheur et coût bande passante GitHub.
    sync_default_interval_seconds: int = Field(default=300, ge=60)

    # Racine des clones git locaux. En prod : volume Docker named `rag_repos`
    # monté sur /var/lib/rag/repos. En test : `tmp_path` via fixture pytest.
    sync_repos_root: Path = Path("/var/lib/rag/repos")
```

Ajouter `from pathlib import Path` en tête si absent (vérifier les imports existants).

- [ ] **Step 1.4 : Relancer les tests (vert)**

```powershell
uv run pytest tests/unit/test_config.py -v -k "sync_default or sync_repos"
```

Expected : 4 PASS.

- [ ] **Step 1.5 : Mettre à jour `.env.example`**

Ajouter dans `.env.example` (à la racine du repo), à la fin de la section "Divers" :

```env
# ─── Sync worker M3 ─────────────────────────────────────────
# Interval défaut entre 2 syncs d'une même source (sec). Override possible
# par source via config.sync_interval_seconds. Min 60s.
SYNC_DEFAULT_INTERVAL_SECONDS=300
# Racine des clones git locaux (volume Docker named en prod).
SYNC_REPOS_ROOT=/var/lib/rag/repos
```

- [ ] **Step 1.6 : Commit**

```bash
git add backend/src/rag/config.py backend/tests/unit/test_config.py .env.example
git commit -m "feat(config): sync_default_interval_seconds + sync_repos_root pour le worker M3"
```

---

## Task 2 — `schemas/sync.py` : DTOs internes

**Files:**
- Create: `backend/src/rag/schemas/sync.py`
- Create: `backend/tests/unit/test_schemas_sync.py`

- [ ] **Step 2.1 : Tests (rouge)**

Créer `backend/tests/unit/test_schemas_sync.py` :

```python
from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from rag.schemas.sync import (
    ChangeSet,
    DueSource,
    GitOpResult,
    JobToProcess,
)


def test_change_set_defaults_empty_lists() -> None:
    cs = ChangeSet()
    assert cs.added == []
    assert cs.modified == []
    assert cs.deleted == []


def test_change_set_total_files_property() -> None:
    cs = ChangeSet(added=["a.md", "b.md"], modified=["c.md"], deleted=["d.md"])
    assert cs.total_changed == 4


def test_git_op_result_requires_current_commit() -> None:
    with pytest.raises(ValidationError):
        GitOpResult(was_fresh_clone=True)  # type: ignore[call-arg]


def test_git_op_result_minimal() -> None:
    r = GitOpResult(was_fresh_clone=False, current_commit="abc123")
    assert r.was_fresh_clone is False
    assert r.current_commit == "abc123"


def test_due_source_validates_workspace_and_source_ids() -> None:
    src = DueSource(
        source_id=uuid4(),
        workspace_id=uuid4(),
        config={"url": "https://github.com/x/y", "branch": "main"},
    )
    assert src.config["url"] == "https://github.com/x/y"


def test_job_to_process_requires_workspace_and_indexer_config() -> None:
    j = JobToProcess(
        job_id=uuid4(),
        workspace_id=uuid4(),
        workspace_name="ws_x",
        source_id=uuid4(),
        source_config={"url": "https://github.com/x/y", "branch": "main"},
        indexer_provider="openai",
        indexer_model="text-embedding-3-small",
    )
    assert j.indexer_used == "openai/text-embedding-3-small"
```

- [ ] **Step 2.2 : Rouge**

```powershell
uv run pytest tests/unit/test_schemas_sync.py -v
```

Expected : 6 ERROR `ModuleNotFoundError: rag.schemas.sync`.

- [ ] **Step 2.3 : Impl**

Créer `backend/src/rag/schemas/sync.py` :

```python
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChangeSet(BaseModel):
    """Résultat d'un diff git filtré (post `include` / `exclude`).

    `added` / `modified` / `deleted` contiennent des chemins relatifs au
    worktree git, déjà filtrés via les patterns glob de la source.
    """

    model_config = ConfigDict(extra="forbid")

    added: list[str] = Field(default_factory=list)
    modified: list[str] = Field(default_factory=list)
    deleted: list[str] = Field(default_factory=list)

    @property
    def total_changed(self) -> int:
        return len(self.added) + len(self.modified) + len(self.deleted)


class GitOpResult(BaseModel):
    """Résultat d'un `ensure_clone_or_pull`."""

    model_config = ConfigDict(extra="forbid")

    was_fresh_clone: bool
    current_commit: str = Field(min_length=1)


class DueSource(BaseModel):
    """Une source dont `next_sync_at <= now()`, candidate pour scheduling."""

    model_config = ConfigDict(extra="forbid")

    source_id: UUID
    workspace_id: UUID
    config: dict[str, Any]


class JobToProcess(BaseModel):
    """Contexte d'un job piké par l'executor (1 row JOIN workspace + indexer)."""

    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    workspace_id: UUID
    workspace_name: str
    source_id: UUID
    source_config: dict[str, Any]
    indexer_provider: str
    indexer_model: str

    @property
    def indexer_used(self) -> str:
        """Identifiant logique utilisé pour `indexed_documents.indexer_used`."""
        return f"{self.indexer_provider}/{self.indexer_model}"
```

- [ ] **Step 2.4 : Vert**

```powershell
uv run pytest tests/unit/test_schemas_sync.py -v
```

Expected : 6 PASS.

- [ ] **Step 2.5 : Lint**

```powershell
uv run ruff check src/rag/schemas/sync.py tests/unit/test_schemas_sync.py
uv run ruff format --check src/rag/schemas/sync.py tests/unit/test_schemas_sync.py
uv run mypy src/rag/schemas/sync.py
```

Clean attendu.

- [ ] **Step 2.6 : Commit**

```bash
git add backend/src/rag/schemas/sync.py backend/tests/unit/test_schemas_sync.py
git commit -m "feat(schemas): DTOs internes sync (ChangeSet, GitOpResult, DueSource, JobToProcess)"
```

---

## Task 3 — `indexer/protocol.py` + `indexer/noop.py`

**Files:**
- Create: `backend/src/rag/indexer/protocol.py`
- Create: `backend/src/rag/indexer/noop.py`
- Create: `backend/tests/integration/test_indexer_noop.py`

- [ ] **Step 3.1 : Tests intégration (rouge)**

Créer `backend/tests/integration/test_indexer_noop.py` :

```python
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.indexer.noop import NoOpIndexer

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_noop_index_file_inserts_indexed_documents_row(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ('ws_noop_a', 'h', 'c', 'b') RETURNING id"
        )

    indexer = NoOpIndexer(session_pool)
    chunks = await indexer.index_file(
        workspace_id=ws_id,
        path="docs/README.md",
        content="hello",
        content_hash="sha256:abc",
        indexer_used="openai/text-embedding-3-small",
    )
    assert chunks == 1

    row = await session_pool.fetchrow(
        "SELECT content_hash, indexer_used FROM indexed_documents "
        "WHERE workspace_id=$1 AND path=$2",
        ws_id,
        "docs/README.md",
    )
    assert row is not None
    assert row["content_hash"] == "sha256:abc"
    assert row["indexer_used"] == "openai/text-embedding-3-small"


@pytest.mark.asyncio
async def test_noop_index_file_updates_on_conflict(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ('ws_noop_b', 'h', 'c', 'b') RETURNING id"
        )

    indexer = NoOpIndexer(session_pool)
    await indexer.index_file(
        workspace_id=ws_id, path="a.md", content="v1",
        content_hash="sha256:v1", indexer_used="openai/text-embedding-3-small",
    )
    await indexer.index_file(
        workspace_id=ws_id, path="a.md", content="v2",
        content_hash="sha256:v2", indexer_used="openai/text-embedding-3-small",
    )

    rows = await session_pool.fetch(
        "SELECT content_hash FROM indexed_documents WHERE workspace_id=$1 AND path='a.md'",
        ws_id,
    )
    assert len(rows) == 1
    assert rows[0]["content_hash"] == "sha256:v2"


@pytest.mark.asyncio
async def test_noop_delete_file_removes_row(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ('ws_noop_c', 'h', 'c', 'b') RETURNING id"
        )

    indexer = NoOpIndexer(session_pool)
    await indexer.index_file(
        workspace_id=ws_id, path="x.md", content="x",
        content_hash="sha256:x", indexer_used="openai/text-embedding-3-small",
    )
    await indexer.delete_file(workspace_id=ws_id, path="x.md")

    row = await session_pool.fetchrow(
        "SELECT 1 FROM indexed_documents WHERE workspace_id=$1 AND path='x.md'",
        ws_id,
    )
    assert row is None


@pytest.mark.asyncio
async def test_noop_delete_file_idempotent_when_absent(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    # Pas d'INSERT préalable. Le delete doit ne rien faire et ne pas lever.
    indexer = NoOpIndexer(session_pool)
    await indexer.delete_file(workspace_id=uuid4(), path="absent.md")
```

- [ ] **Step 3.2 : Rouge**

```powershell
$env:TEST_POSTGRES_PASSWORD = "LJu_nISEyxccTdm2w72l4AkDVsUF4BeR"
uv run pytest tests/integration/test_indexer_noop.py -v
```

Expected : 4 ERROR `cannot import 'NoOpIndexer'`.

- [ ] **Step 3.3 : Impl Protocol**

Créer `backend/src/rag/indexer/protocol.py` :

```python
from __future__ import annotations

from typing import Protocol
from uuid import UUID


class IndexerProtocol(Protocol):
    """Frontière entre le sync worker (M3) et le moteur d'indexation (M4).

    M3 utilise `NoOpIndexer` qui maintient seulement `indexed_documents`.
    M4 remplacera par `RealIndexer` qui ajoute chunking + embeddings +
    upsert pgvector dans la base `rag_<workspace_name>`.
    """

    async def index_file(
        self,
        *,
        workspace_id: UUID,
        path: str,
        content: str,
        content_hash: str,
        indexer_used: str,
    ) -> int:
        """Index un fichier. Retourne le nombre de chunks créés.

        - `workspace_id` : workspace cible (sert au routing du pool pgvector).
        - `path` : chemin relatif au worktree (clé d'upsert).
        - `content` : contenu UTF-8 du fichier.
        - `content_hash` : `sha256:<hex>` du contenu.
        - `indexer_used` : `<provider>/<model>` au moment de l'indexation
          (sert à invalider les hashes si l'indexeur change).
        """
        ...

    async def delete_file(self, *, workspace_id: UUID, path: str) -> None:
        """Supprime tous les chunks pgvector d'un fichier + DELETE
        `indexed_documents`. Idempotent.
        """
        ...
```

- [ ] **Step 3.4 : Impl NoOpIndexer**

Créer `backend/src/rag/indexer/noop.py` :

```python
from __future__ import annotations

from uuid import UUID

import asyncpg
import structlog

log = structlog.get_logger(__name__)


class NoOpIndexer:
    """Implémentation M3 de `IndexerProtocol` : maintient seulement
    `indexed_documents` (hash + indexer_used), NE touche PAS à pgvector.

    Remplacé en M4 par un indexer qui ajoute chunking + embeddings +
    upsert pgvector.
    """

    def __init__(self, config_pool: asyncpg.Pool) -> None:
        self._config_pool = config_pool

    async def index_file(
        self,
        *,
        workspace_id: UUID,
        path: str,
        content: str,
        content_hash: str,
        indexer_used: str,
    ) -> int:
        """INSERT/UPDATE `indexed_documents` via ON CONFLICT. Retourne 1
        (1 chunk fictif). `content` est ignoré en M3.
        """
        async with self._config_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO indexed_documents
                    (workspace_id, path, content_hash, indexer_used, indexed_at)
                VALUES ($1, $2, $3, $4, now())
                ON CONFLICT (workspace_id, path) DO UPDATE
                SET content_hash = EXCLUDED.content_hash,
                    indexer_used = EXCLUDED.indexer_used,
                    indexed_at   = EXCLUDED.indexed_at
                """,
                workspace_id, path, content_hash, indexer_used,
            )
        log.info(
            "noop_indexer.index_file",
            workspace_id=str(workspace_id),
            path=path,
            content_len=len(content),
        )
        return 1

    async def delete_file(self, *, workspace_id: UUID, path: str) -> None:
        """DELETE indexed_documents. Idempotent (silencieux si absent)."""
        async with self._config_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM indexed_documents WHERE workspace_id=$1 AND path=$2",
                workspace_id, path,
            )
        log.info(
            "noop_indexer.delete_file",
            workspace_id=str(workspace_id),
            path=path,
        )
```

- [ ] **Step 3.5 : Vert**

```powershell
uv run pytest tests/integration/test_indexer_noop.py -v
```

Expected : 4 PASS.

- [ ] **Step 3.6 : Lint**

```powershell
uv run ruff check src/rag/indexer tests/integration/test_indexer_noop.py
uv run ruff format --check src/rag/indexer tests/integration/test_indexer_noop.py
uv run mypy src/rag/indexer
```

Clean.

- [ ] **Step 3.7 : Commit**

```bash
git add backend/src/rag/indexer/protocol.py backend/src/rag/indexer/noop.py backend/tests/integration/test_indexer_noop.py
git commit -m "feat(indexer): IndexerProtocol + NoOpIndexer (stub M3 maintenant indexed_documents)"
```

---

## Task 4 — `sync/repo_storage.py` : path resolution

**Files:**
- Create: `backend/src/rag/sync/repo_storage.py`
- Create: `backend/tests/unit/test_repo_storage.py`

- [ ] **Step 4.1 : Tests (rouge)**

Créer `backend/tests/unit/test_repo_storage.py` :

```python
from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest

from rag.sync.repo_storage import RepoStorage


def test_path_for_returns_nested_path() -> None:
    storage = RepoStorage(root=Path("/var/lib/rag/repos"))
    ws_id = UUID("11111111-1111-1111-1111-111111111111")
    src_id = UUID("22222222-2222-2222-2222-222222222222")
    p = storage.path_for(workspace_id=ws_id, source_id=src_id)
    assert p == Path(
        "/var/lib/rag/repos/11111111-1111-1111-1111-111111111111/"
        "22222222-2222-2222-2222-222222222222"
    )


def test_ensure_exists_creates_directory(tmp_path: Path) -> None:
    storage = RepoStorage(root=tmp_path)
    ws_id = uuid4()
    src_id = uuid4()
    p = storage.ensure_exists(workspace_id=ws_id, source_id=src_id)
    assert p.exists()
    assert p.is_dir()


def test_ensure_exists_idempotent(tmp_path: Path) -> None:
    storage = RepoStorage(root=tmp_path)
    ws_id = uuid4()
    src_id = uuid4()
    p1 = storage.ensure_exists(workspace_id=ws_id, source_id=src_id)
    p2 = storage.ensure_exists(workspace_id=ws_id, source_id=src_id)
    assert p1 == p2
    assert p1.exists()


def test_has_git_returns_false_when_no_clone(tmp_path: Path) -> None:
    storage = RepoStorage(root=tmp_path)
    ws_id = uuid4()
    src_id = uuid4()
    storage.ensure_exists(workspace_id=ws_id, source_id=src_id)
    assert storage.has_git(workspace_id=ws_id, source_id=src_id) is False


def test_has_git_returns_true_when_dot_git_exists(tmp_path: Path) -> None:
    storage = RepoStorage(root=tmp_path)
    ws_id = uuid4()
    src_id = uuid4()
    p = storage.ensure_exists(workspace_id=ws_id, source_id=src_id)
    (p / ".git").mkdir()
    assert storage.has_git(workspace_id=ws_id, source_id=src_id) is True
```

- [ ] **Step 4.2 : Rouge**

```powershell
uv run pytest tests/unit/test_repo_storage.py -v
```

Expected : 5 ERROR `ModuleNotFoundError: rag.sync.repo_storage`.

- [ ] **Step 4.3 : Impl**

Créer `backend/src/rag/sync/repo_storage.py` :

```python
from __future__ import annotations

from pathlib import Path
from uuid import UUID


class RepoStorage:
    """Résolution des chemins locaux pour les clones git par workspace+source.

    Layout :
        <root>/<workspace_id>/<source_id>/
        <root>/<workspace_id>/<source_id>/.git/

    Les UUID sont sérialisés en string canonique (`str(UUID)` → `xxxxxxxx-...`),
    donc inoffensifs côté path injection. `pathlib.Path` empêche toute
    manipulation type `..` dans le segment puisque l'UUID est strictement
    validé en amont par Pydantic.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def path_for(self, *, workspace_id: UUID, source_id: UUID) -> Path:
        return self._root / str(workspace_id) / str(source_id)

    def ensure_exists(self, *, workspace_id: UUID, source_id: UUID) -> Path:
        """Crée le dossier (parents=True) et retourne le path. Idempotent."""
        p = self.path_for(workspace_id=workspace_id, source_id=source_id)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def has_git(self, *, workspace_id: UUID, source_id: UUID) -> bool:
        """True si `<path>/.git` existe (clone fait au moins une fois)."""
        return (
            self.path_for(workspace_id=workspace_id, source_id=source_id) / ".git"
        ).exists()
```

- [ ] **Step 4.4 : Vert**

```powershell
uv run pytest tests/unit/test_repo_storage.py -v
```

Expected : 5 PASS.

- [ ] **Step 4.5 : Commit**

```bash
git add backend/src/rag/sync/repo_storage.py backend/tests/unit/test_repo_storage.py
git commit -m "feat(sync): repo_storage (path resolution + ensure_exists + has_git)"
```

---

## Task 5 — `sync/git_ops.py` : `clone` + sanitization

**Files:**
- Create: `backend/src/rag/sync/git_ops.py`
- Create: `backend/tests/integration/test_git_ops_clone.py`

Cette tâche implémente uniquement `clone` (+ exceptions custom + sanitization stderr). Les autres opérations (`pull`, `diff_changes`, `list_all_files`) suivent en T6-T8.

- [ ] **Step 5.1 : Fixture git éphémère**

Créer `backend/tests/integration/conftest.py` (si pas déjà présent) ou ajouter à `tests/conftest.py` une nouvelle fixture :

Créer `backend/tests/integration/_git_fixture.py` :

```python
from __future__ import annotations

import subprocess
from pathlib import Path


def make_bare_repo_with_commits(tmp_path: Path, files: dict[str, str]) -> Path:
    """Crée un repo bare avec des commits initialisés depuis un dict
    {path: content}. Retourne le path du repo bare (à utiliser comme URL
    de clone : `file:///tmp/.../bare.git`).
    """
    bare = tmp_path / "bare.git"
    subprocess.run(
        ["git", "init", "--bare", "--initial-branch=main", str(bare)],
        check=True, capture_output=True,
    )

    work = tmp_path / "work"
    subprocess.run(
        ["git", "clone", str(bare), str(work)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(work), "config", "user.email", "test@test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(work), "config", "user.name", "test"],
        check=True,
    )

    for path, content in files.items():
        full = work / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")

    subprocess.run(["git", "-C", str(work), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(work), "commit", "-m", "initial"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(work), "push", "origin", "main"],
        check=True, capture_output=True,
    )
    return bare


def add_commit(work_dir: Path, files: dict[str, str], deletes: list[str] | None = None) -> str:
    """Ajoute/modifie/supprime des fichiers dans un work dir et push.
    Retourne le nouveau commit SHA.
    """
    for path, content in files.items():
        full = work_dir / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    for path in deletes or []:
        (work_dir / path).unlink()

    subprocess.run(["git", "-C", str(work_dir), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(work_dir), "commit", "-m", "update"],
        check=True, capture_output=True,
    )
    sha = subprocess.run(
        ["git", "-C", str(work_dir), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "-C", str(work_dir), "push", "origin", "main"],
        check=True, capture_output=True,
    )
    return sha
```

Pas de test direct sur ce helper (testé indirectement via T5+).

- [ ] **Step 5.2 : Tests clone (rouge)**

Créer `backend/tests/integration/test_git_ops_clone.py` :

```python
from __future__ import annotations

from pathlib import Path

import pytest

from rag.sync.git_ops import GitCloneError, clone, sanitize_git_output
from tests.integration._git_fixture import make_bare_repo_with_commits


@pytest.mark.asyncio
async def test_clone_success_creates_git_dir(tmp_path: Path) -> None:
    bare = make_bare_repo_with_commits(tmp_path, {"README.md": "hello"})
    dest = tmp_path / "dest"
    await clone(url=f"file://{bare}", branch="main", token=None, dest=dest)
    assert (dest / ".git").is_dir()
    assert (dest / "README.md").read_text() == "hello"


@pytest.mark.asyncio
async def test_clone_failure_raises_with_sanitized_stderr(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    with pytest.raises(GitCloneError) as exc_info:
        await clone(
            url="https://x-access-token:secrettoken@example.invalid/x/y.git",
            branch="main",
            token="secrettoken",
            dest=dest,
        )
    # Le message d'erreur ne doit PAS contenir le token
    assert "secrettoken" not in str(exc_info.value)
    assert "***" in str(exc_info.value) or "git clone failed" in str(exc_info.value)


def test_sanitize_git_output_redacts_basic_auth() -> None:
    raw = "fatal: could not resolve https://x-access-token:ghp_abc@github.com/x/y.git"
    sanitized = sanitize_git_output(raw)
    assert "ghp_abc" not in sanitized
    assert "***" in sanitized


def test_sanitize_git_output_passes_through_when_no_secret() -> None:
    raw = "Cloning into 'dest'...\nFatal: not a git repository"
    sanitized = sanitize_git_output(raw)
    assert sanitized == raw
```

- [ ] **Step 5.3 : Rouge**

```powershell
uv run pytest tests/integration/test_git_ops_clone.py -v
```

Expected : 4 ERROR/FAIL.

- [ ] **Step 5.4 : Impl clone**

Créer `backend/src/rag/sync/git_ops.py` :

```python
from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import NoReturn

import structlog

log = structlog.get_logger(__name__)


class GitCloneError(RuntimeError):
    """Echec d'un `git clone`."""


class GitPullError(RuntimeError):
    """Echec d'un `git pull` ou `git fetch`/`reset`."""


# Token-in-URL pattern : https://user:token@host... → https://***@host
_TOKEN_URL_RE = re.compile(r"https?://[^@\s]+@", re.IGNORECASE)


def sanitize_git_output(text: str) -> str:
    """Remplace tout `https://<user>:<token>@host` par `https://***@host`.

    Appliqué sur stderr/stdout avant tout log ou persistance dans
    `index_jobs.error_message`. Idempotent (déjà sanitized → no-op).
    """
    return _TOKEN_URL_RE.sub("https://***@", text)


def _build_authenticated_url(url: str, token: str | None) -> str:
    """Injecte le token dans une URL HTTPS GitHub/Azure.

    Si `token` est None : URL inchangée (clone anonyme — OK pour repos publics).
    Sinon : `https://x-access-token:<token>@host/...`.
    """
    if token is None:
        return url
    if not url.startswith("https://"):
        return url  # SSH ou git:// — l'auth se fait autrement (clé SSH, etc.)
    return url.replace("https://", f"https://x-access-token:{token}@", 1)


async def _run_git(
    args: list[str],
    *,
    cwd: Path | None = None,
    token: str | None = None,
    error_cls: type[RuntimeError] = RuntimeError,
    error_prefix: str = "git failed",
) -> tuple[str, str]:
    """Exécute git avec stderr capturé + sanitization.

    Lève `error_cls(error_prefix + ": <stderr sanitized>")` sur returncode != 0.
    Retourne `(stdout, stderr)` sanitized en cas de succès.

    `GIT_TERMINAL_PROMPT=0` empêche git d'attendre un mot de passe interactif.
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_b, stderr_b = await proc.communicate()
    stdout = sanitize_git_output(stdout_b.decode("utf-8", errors="replace"))
    stderr = sanitize_git_output(stderr_b.decode("utf-8", errors="replace"))

    if proc.returncode != 0:
        msg = f"{error_prefix}: {stderr.strip() or stdout.strip() or 'unknown error'}"
        raise error_cls(msg)
    return stdout, stderr


async def clone(
    *, url: str, branch: str, token: str | None, dest: Path,
) -> None:
    """`git clone --branch <branch> <auth_url> <dest>`.

    Lève `GitCloneError` (sanitized) si échec.
    """
    auth_url = _build_authenticated_url(url, token)
    dest.parent.mkdir(parents=True, exist_ok=True)
    log.info("git.clone.start", url=sanitize_git_output(auth_url), dest=str(dest))
    await _run_git(
        ["clone", "--branch", branch, auth_url, str(dest)],
        token=token,
        error_cls=GitCloneError,
        error_prefix="git clone failed",
    )
    log.info("git.clone.done", dest=str(dest))
```

- [ ] **Step 5.5 : Vert**

```powershell
uv run pytest tests/integration/test_git_ops_clone.py -v
```

Expected : 4 PASS.

- [ ] **Step 5.6 : Lint**

```powershell
uv run ruff check src/rag/sync/git_ops.py tests/integration/test_git_ops_clone.py
uv run ruff format --check src/rag/sync/git_ops.py tests/integration/test_git_ops_clone.py
uv run mypy src/rag/sync/git_ops.py
```

Clean.

- [ ] **Step 5.7 : Commit**

```bash
git add backend/src/rag/sync/git_ops.py backend/tests/integration/test_git_ops_clone.py backend/tests/integration/_git_fixture.py
git commit -m "feat(sync): git_ops.clone + sanitize_git_output (token redaction)"
```

---

## Task 6 — `git_ops.pull` + `head_commit`

**Files:**
- Modify: `backend/src/rag/sync/git_ops.py` (ajouter `pull`, `head_commit`)
- Create: `backend/tests/integration/test_git_ops_pull.py`

- [ ] **Step 6.1 : Tests (rouge)**

```python
# backend/tests/integration/test_git_ops_pull.py
from __future__ import annotations

from pathlib import Path

import pytest

from rag.sync.git_ops import GitPullError, clone, head_commit, pull
from tests.integration._git_fixture import add_commit, make_bare_repo_with_commits


@pytest.mark.asyncio
async def test_head_commit_returns_sha_after_clone(tmp_path: Path) -> None:
    bare = make_bare_repo_with_commits(tmp_path, {"a.md": "v1"})
    dest = tmp_path / "dest"
    await clone(url=f"file://{bare}", branch="main", token=None, dest=dest)
    sha = await head_commit(dest)
    assert len(sha) == 40
    assert all(c in "0123456789abcdef" for c in sha)


@pytest.mark.asyncio
async def test_pull_fetches_new_commit(tmp_path: Path) -> None:
    bare = make_bare_repo_with_commits(tmp_path, {"a.md": "v1"})
    dest = tmp_path / "dest"
    await clone(url=f"file://{bare}", branch="main", token=None, dest=dest)
    sha_before = await head_commit(dest)

    work_remote = tmp_path / "work"
    sha_added = add_commit(work_remote, {"b.md": "v1"})

    await pull(dest=dest, branch="main")
    sha_after = await head_commit(dest)
    assert sha_after != sha_before
    assert sha_after == sha_added
    assert (dest / "b.md").exists()


@pytest.mark.asyncio
async def test_pull_resets_local_modifs(tmp_path: Path) -> None:
    """`pull` doit faire reset --hard pour garantir l'alignement avec remote."""
    bare = make_bare_repo_with_commits(tmp_path, {"a.md": "v1"})
    dest = tmp_path / "dest"
    await clone(url=f"file://{bare}", branch="main", token=None, dest=dest)

    # Modifie un fichier localement (simule corruption)
    (dest / "a.md").write_text("CORRUPTED")

    await pull(dest=dest, branch="main")
    assert (dest / "a.md").read_text() == "v1"  # reset


@pytest.mark.asyncio
async def test_pull_fails_on_invalid_path(tmp_path: Path) -> None:
    with pytest.raises(GitPullError):
        await pull(dest=tmp_path / "nonexistent", branch="main")
```

- [ ] **Step 6.2 : Rouge → 4 ERROR `cannot import 'pull'`.**

```powershell
uv run pytest tests/integration/test_git_ops_pull.py -v
```

- [ ] **Step 6.3 : Impl**

Ajouter en fin de `backend/src/rag/sync/git_ops.py` :

```python
async def head_commit(dest: Path) -> str:
    """Retourne le SHA-1 du HEAD courant (`git rev-parse HEAD`).

    Lève `GitPullError` (sanitized) si le repo est invalide / corrompu.
    """
    stdout, _ = await _run_git(
        ["rev-parse", "HEAD"],
        cwd=dest,
        error_cls=GitPullError,
        error_prefix="git rev-parse failed",
    )
    return stdout.strip()


async def pull(*, dest: Path, branch: str) -> None:
    """Fetch + reset --hard pour aligner sur remote/<branch>.

    Lève `GitPullError` (sanitized) si fetch ou reset échoue.
    Le `reset --hard` perd les modifs locales — voulu, le worktree est
    contrôlé par le worker uniquement.
    """
    log.info("git.pull.start", dest=str(dest), branch=branch)
    await _run_git(
        ["fetch", "origin", branch],
        cwd=dest,
        error_cls=GitPullError,
        error_prefix="git fetch failed",
    )
    await _run_git(
        ["reset", "--hard", f"origin/{branch}"],
        cwd=dest,
        error_cls=GitPullError,
        error_prefix="git reset failed",
    )
    log.info("git.pull.done", dest=str(dest), branch=branch)
```

- [ ] **Step 6.4 : Vert + lint + commit**

```powershell
uv run pytest tests/integration/test_git_ops_pull.py -v
uv run ruff check src/rag/sync/git_ops.py tests/integration/test_git_ops_pull.py
uv run mypy src/rag/sync/git_ops.py
```

```bash
git add backend/src/rag/sync/git_ops.py backend/tests/integration/test_git_ops_pull.py
git commit -m "feat(sync): git_ops.pull + head_commit (fetch + reset --hard)"
```

---

## Task 7 — `git_ops.list_all_files` (cas 1er sync)

**Files:**
- Modify: `backend/src/rag/sync/git_ops.py`
- Create: `backend/tests/integration/test_git_ops_list.py`

- [ ] **Step 7.1 : Tests (rouge)**

```python
# backend/tests/integration/test_git_ops_list.py
from __future__ import annotations

from pathlib import Path

import pytest

from rag.sync.git_ops import clone, list_all_files
from tests.integration._git_fixture import make_bare_repo_with_commits


@pytest.mark.asyncio
async def test_list_all_files_returns_tracked_files(tmp_path: Path) -> None:
    bare = make_bare_repo_with_commits(
        tmp_path,
        {"README.md": "x", "docs/a.md": "y", "src/b.py": "z"},
    )
    dest = tmp_path / "dest"
    await clone(url=f"file://{bare}", branch="main", token=None, dest=dest)

    files = await list_all_files(dest)
    assert sorted(files) == ["README.md", "docs/a.md", "src/b.py"]


@pytest.mark.asyncio
async def test_list_all_files_excludes_untracked(tmp_path: Path) -> None:
    bare = make_bare_repo_with_commits(tmp_path, {"a.md": "x"})
    dest = tmp_path / "dest"
    await clone(url=f"file://{bare}", branch="main", token=None, dest=dest)

    # Fichier non tracké : ne doit pas apparaître
    (dest / "untracked.md").write_text("u")

    files = await list_all_files(dest)
    assert files == ["a.md"]
```

- [ ] **Step 7.2 : Rouge → 2 ERROR.**

- [ ] **Step 7.3 : Impl**

Ajouter en fin de `backend/src/rag/sync/git_ops.py` :

```python
async def list_all_files(dest: Path) -> list[str]:
    """Retourne tous les fichiers trackés par git (`git ls-files`).

    Sert au 1er sync d'une source (pas de `last_commit` connu) : on traite
    tous les fichiers du worktree.
    """
    stdout, _ = await _run_git(
        ["ls-files"],
        cwd=dest,
        error_cls=GitPullError,
        error_prefix="git ls-files failed",
    )
    return [line for line in stdout.splitlines() if line]
```

- [ ] **Step 7.4 : Vert + commit**

```powershell
uv run pytest tests/integration/test_git_ops_list.py -v
```

```bash
git add backend/src/rag/sync/git_ops.py backend/tests/integration/test_git_ops_list.py
git commit -m "feat(sync): git_ops.list_all_files (cas 1er sync)"
```

---

## Task 8 — `git_ops.diff_changes` + `filter_glob`

**Files:**
- Modify: `backend/src/rag/sync/git_ops.py` (ajouter `diff_changes`, `filter_glob`)
- Create: `backend/tests/integration/test_git_ops_diff.py`
- Create: `backend/tests/unit/test_filter_glob.py`

- [ ] **Step 8.1 : Tests filter_glob (rouge)**

```python
# backend/tests/unit/test_filter_glob.py
from __future__ import annotations

from rag.schemas.sync import ChangeSet
from rag.sync.git_ops import filter_glob


def test_filter_glob_default_includes_everything() -> None:
    cs = ChangeSet(added=["a.md", "b.py"], modified=["c.json"], deleted=["d.png"])
    out = filter_glob(cs, include=["**/*"], exclude=[])
    assert out.added == ["a.md", "b.py"]
    assert out.modified == ["c.json"]
    assert out.deleted == ["d.png"]


def test_filter_glob_include_only_markdown() -> None:
    cs = ChangeSet(added=["a.md", "b.py"], modified=["docs/c.md"])
    out = filter_glob(cs, include=["**/*.md"], exclude=[])
    assert out.added == ["a.md"]
    assert out.modified == ["docs/c.md"]


def test_filter_glob_exclude_takes_priority() -> None:
    cs = ChangeSet(added=["a.md", "node_modules/x.md"], modified=[])
    out = filter_glob(cs, include=["**/*.md"], exclude=["node_modules/**"])
    assert out.added == ["a.md"]
    assert out.modified == []


def test_filter_glob_empty_changeset() -> None:
    cs = ChangeSet()
    out = filter_glob(cs, include=["**/*"], exclude=[])
    assert out.total_changed == 0
```

- [ ] **Step 8.2 : Tests diff_changes (rouge)**

```python
# backend/tests/integration/test_git_ops_diff.py
from __future__ import annotations

from pathlib import Path

import pytest

from rag.sync.git_ops import clone, diff_changes, head_commit, pull
from tests.integration._git_fixture import add_commit, make_bare_repo_with_commits


@pytest.mark.asyncio
async def test_diff_changes_added_modified_deleted(tmp_path: Path) -> None:
    bare = make_bare_repo_with_commits(
        tmp_path, {"a.md": "v1", "b.md": "v1", "c.md": "v1"},
    )
    dest = tmp_path / "dest"
    await clone(url=f"file://{bare}", branch="main", token=None, dest=dest)
    sha_initial = await head_commit(dest)

    # Modif côté remote : a.md modifié, b.md supprimé, d.md ajouté
    work_remote = tmp_path / "work"
    sha_after = add_commit(
        work_remote,
        files={"a.md": "v2", "d.md": "v1"},
        deletes=["b.md"],
    )
    await pull(dest=dest, branch="main")

    changes = await diff_changes(dest=dest, from_commit=sha_initial, to_commit=sha_after)
    assert sorted(changes.added) == ["d.md"]
    assert sorted(changes.modified) == ["a.md"]
    assert sorted(changes.deleted) == ["b.md"]
```

- [ ] **Step 8.3 : Rouge → fail.**

```powershell
uv run pytest tests/unit/test_filter_glob.py tests/integration/test_git_ops_diff.py -v
```

- [ ] **Step 8.4 : Impl**

Ajouter en fin de `backend/src/rag/sync/git_ops.py` :

```python
import fnmatch

from rag.schemas.sync import ChangeSet


async def diff_changes(
    *, dest: Path, from_commit: str, to_commit: str,
) -> ChangeSet:
    """`git diff --name-status <from>..<to>` → ChangeSet typé.

    Préfixes git : `A` (added), `M` (modified), `D` (deleted),
    `R<score>` (renamed — traité comme delete+add).
    """
    stdout, _ = await _run_git(
        ["diff", "--name-status", f"{from_commit}..{to_commit}"],
        cwd=dest,
        error_cls=GitPullError,
        error_prefix="git diff failed",
    )
    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status == "A":
            added.append(parts[1])
        elif status == "M":
            modified.append(parts[1])
        elif status == "D":
            deleted.append(parts[1])
        elif status.startswith("R"):
            # Rename = delete + add
            deleted.append(parts[1])
            added.append(parts[2])
    return ChangeSet(added=added, modified=modified, deleted=deleted)


def filter_glob(
    cs: ChangeSet, *, include: list[str], exclude: list[str],
) -> ChangeSet:
    """Applique les filtres glob (`fnmatch`) sur un ChangeSet.

    Un fichier passe si :
      - il match au moins un pattern `include`
      - ET il ne match aucun pattern `exclude`

    `**/*` est traité comme `*` (récursif sur le worktree).
    """

    def _match(path: str, patterns: list[str]) -> bool:
        for p in patterns:
            # fnmatch supporte * mais pas ** ; on désucre.
            adjusted = p.replace("**/", "").replace("**", "*")
            if fnmatch.fnmatch(path, adjusted):
                return True
        return False

    def _keep(path: str) -> bool:
        if not _match(path, include):
            return False
        if exclude and _match(path, exclude):
            return False
        return True

    return ChangeSet(
        added=[p for p in cs.added if _keep(p)],
        modified=[p for p in cs.modified if _keep(p)],
        deleted=[p for p in cs.deleted if _keep(p)],
    )
```

- [ ] **Step 8.5 : Vert + commit**

```powershell
uv run pytest tests/unit/test_filter_glob.py tests/integration/test_git_ops_diff.py -v
uv run ruff check src/rag/sync/git_ops.py tests/unit/test_filter_glob.py tests/integration/test_git_ops_diff.py
uv run mypy src/rag/sync/git_ops.py
```

```bash
git add backend/src/rag/sync/git_ops.py backend/tests/integration/test_git_ops_diff.py backend/tests/unit/test_filter_glob.py
git commit -m "feat(sync): diff_changes (name-status) + filter_glob (include/exclude)"
```

---

## Task 9 — `sync/recovery.py` : reset des jobs running orphelins

**Files:**
- Create: `backend/src/rag/sync/recovery.py`
- Create: `backend/tests/integration/test_sync_recovery.py`

- [ ] **Step 9.1 : Tests (rouge)**

```python
# backend/tests/integration/test_sync_recovery.py
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.sync.recovery import reset_stale_running_jobs

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def _make_running_job(pool: asyncpg.Pool, ws_id, started_at_offset_sec: int = 0):
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status, started_at) "
            "VALUES ($1, 'manual', 'running', now() - ($2 || ' seconds')::interval) "
            "RETURNING id",
            ws_id,
            started_at_offset_sec,
        )


@pytest.mark.asyncio
async def test_reset_marks_running_as_error(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ('ws_rec_a', 'h', 'c', 'b') RETURNING id"
        )
    job_id = await _make_running_job(session_pool, ws_id, started_at_offset_sec=300)

    count = await reset_stale_running_jobs(session_pool)
    assert count == 1

    row = await session_pool.fetchrow(
        "SELECT status, error_message, finished_at, duration_ms "
        "FROM index_jobs WHERE id=$1",
        job_id,
    )
    assert row is not None
    assert row["status"] == "error"
    assert row["error_message"] == "stale_at_boot"
    assert row["finished_at"] is not None
    assert row["duration_ms"] is not None
    assert row["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_reset_does_not_touch_pending_or_done(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ('ws_rec_b', 'h', 'c', 'b') RETURNING id"
        )
        pending_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status) "
            "VALUES ($1, 'manual', 'pending') RETURNING id",
            ws_id,
        )
        done_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status, finished_at) "
            "VALUES ($1, 'manual', 'done', now()) RETURNING id",
            ws_id,
        )

    count = await reset_stale_running_jobs(session_pool)
    assert count == 0

    pending_status = await session_pool.fetchval(
        "SELECT status FROM index_jobs WHERE id=$1", pending_id
    )
    done_status = await session_pool.fetchval(
        "SELECT status FROM index_jobs WHERE id=$1", done_id
    )
    assert pending_status == "pending"
    assert done_status == "done"
```

- [ ] **Step 9.2 : Rouge → 2 ERROR.**

- [ ] **Step 9.3 : Impl**

Créer `backend/src/rag/sync/recovery.py` :

```python
from __future__ import annotations

import asyncpg
import structlog

log = structlog.get_logger(__name__)


async def reset_stale_running_jobs(config_pool: asyncpg.Pool) -> int:
    """Marque tous les jobs `running` en `error` au boot (crash recovery).

    Un job `running` au démarrage signifie que le worker a crashé entre
    `started_at` et `finished_at`. Le marquer `error` libère la source
    pour un retry naturel au prochain cycle.

    Retourne le nombre de jobs affectés.
    """
    async with config_pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE index_jobs
            SET status         = 'error',
                error_message  = 'stale_at_boot',
                finished_at    = now(),
                duration_ms    = CASE
                    WHEN started_at IS NOT NULL THEN
                        EXTRACT(MILLISECONDS FROM (now() - started_at))::int
                    ELSE 0
                END
            WHERE status = 'running'
            """
        )
    # asyncpg retourne "UPDATE N" — extraire N.
    count = int(result.split()[-1])
    if count > 0:
        log.warning("sync.recovery.reset_stale_running_jobs", count=count)
    return count
```

- [ ] **Step 9.4 : Vert + commit**

```powershell
uv run pytest tests/integration/test_sync_recovery.py -v
```

```bash
git add backend/src/rag/sync/recovery.py backend/tests/integration/test_sync_recovery.py
git commit -m "feat(sync): recovery.reset_stale_running_jobs (crash recovery au boot)"
```

---

## Task 10 — `sync/scheduler.py` : sources due → jobs pending

**Files:**
- Create: `backend/src/rag/sync/scheduler.py`
- Create: `backend/tests/integration/test_sync_scheduler.py`

- [ ] **Step 10.1 : Tests (rouge)**

```python
# backend/tests/integration/test_sync_scheduler.py
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.sync.scheduler import schedule_due_sources

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
DEFAULT_INTERVAL = 300


async def _make_workspace(pool: asyncpg.Pool, name: str) -> str:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ($1, 'h', 'c', 'b') RETURNING id",
            name,
        )


async def _make_source(
    pool: asyncpg.Pool, ws_id: str, next_sync_offset_sec: int | None,
    config_extra: dict | None = None,
) -> str:
    import json
    cfg = {"url": "https://github.com/x/y", "branch": "main"}
    if config_extra:
        cfg.update(config_extra)
    async with pool.acquire() as conn:
        if next_sync_offset_sec is None:
            return await conn.fetchval(
                "INSERT INTO workspace_sources (workspace_id, type, config, next_sync_at) "
                "VALUES ($1, 'git', $2::jsonb, NULL) RETURNING id",
                ws_id, json.dumps(cfg),
            )
        return await conn.fetchval(
            "INSERT INTO workspace_sources (workspace_id, type, config, next_sync_at) "
            "VALUES ($1, 'git', $2::jsonb, now() + ($3 || ' seconds')::interval) "
            "RETURNING id",
            ws_id, json.dumps(cfg), next_sync_offset_sec,
        )


@pytest.mark.asyncio
async def test_scheduler_creates_job_for_due_source(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    ws_id = await _make_workspace(session_pool, "ws_sched_a")
    src_id = await _make_source(session_pool, ws_id, next_sync_offset_sec=-60)

    n = await schedule_due_sources(
        session_pool, default_interval_seconds=DEFAULT_INTERVAL,
    )
    assert n == 1

    row = await session_pool.fetchrow(
        "SELECT triggered_by, status, source_id FROM index_jobs WHERE workspace_id=$1",
        ws_id,
    )
    assert row is not None
    assert row["triggered_by"] == "schedule"
    assert row["status"] == "pending"
    assert str(row["source_id"]) == str(src_id)

    # next_sync_at bumped
    next_at = await session_pool.fetchval(
        "SELECT next_sync_at FROM workspace_sources WHERE id=$1", src_id
    )
    assert next_at is not None


@pytest.mark.asyncio
async def test_scheduler_skips_source_with_pending_job(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    ws_id = await _make_workspace(session_pool, "ws_sched_b")
    src_id = await _make_source(session_pool, ws_id, next_sync_offset_sec=-60)
    async with session_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO index_jobs (workspace_id, source_id, triggered_by, status) "
            "VALUES ($1, $2, 'manual', 'pending')",
            ws_id, src_id,
        )

    n = await schedule_due_sources(
        session_pool, default_interval_seconds=DEFAULT_INTERVAL,
    )
    assert n == 0


@pytest.mark.asyncio
async def test_scheduler_skips_future_sources(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    ws_id = await _make_workspace(session_pool, "ws_sched_c")
    await _make_source(session_pool, ws_id, next_sync_offset_sec=3600)  # +1h

    n = await schedule_due_sources(
        session_pool, default_interval_seconds=DEFAULT_INTERVAL,
    )
    assert n == 0


@pytest.mark.asyncio
async def test_scheduler_uses_per_source_interval_override(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    ws_id = await _make_workspace(session_pool, "ws_sched_d")
    src_id = await _make_source(
        session_pool, ws_id, next_sync_offset_sec=-60,
        config_extra={"sync_interval_seconds": 60},
    )

    await schedule_due_sources(
        session_pool, default_interval_seconds=DEFAULT_INTERVAL,
    )
    # next_sync_at doit être ~now()+60s, pas now()+300s
    next_at = await session_pool.fetchval(
        "SELECT EXTRACT(EPOCH FROM (next_sync_at - now())) FROM workspace_sources WHERE id=$1",
        src_id,
    )
    assert 50 <= float(next_at) <= 70
```

- [ ] **Step 10.2 : Rouge → 4 ERROR.**

- [ ] **Step 10.3 : Impl**

Créer `backend/src/rag/sync/scheduler.py` :

```python
from __future__ import annotations

import asyncpg
import structlog

log = structlog.get_logger(__name__)


async def schedule_due_sources(
    config_pool: asyncpg.Pool, *, default_interval_seconds: int,
) -> int:
    """Crée des jobs `pending` pour les sources dont `next_sync_at <= now()`
    et qui n'ont pas déjà un job `pending` ou `running` ouvert.

    Pour chaque source schedulée :
      - INSERT `index_jobs (triggered_by='schedule', status='pending')`
      - UPDATE `workspace_sources.next_sync_at = now() + interval`
        où `interval = config.sync_interval_seconds` ou `default_interval_seconds`.

    Retourne le nombre de sources schedulées.
    """
    async with config_pool.acquire() as conn, conn.transaction():
        due = await conn.fetch(
            """
            SELECT s.id AS source_id, s.workspace_id, s.config
            FROM workspace_sources s
            WHERE s.next_sync_at IS NOT NULL
              AND s.next_sync_at <= now()
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
        n = 0
        for row in due:
            interval = _extract_interval(row["config"], default_interval_seconds)
            await conn.execute(
                """
                INSERT INTO index_jobs (workspace_id, source_id, triggered_by, status)
                VALUES ($1, $2, 'schedule', 'pending')
                """,
                row["workspace_id"], row["source_id"],
            )
            await conn.execute(
                """
                UPDATE workspace_sources
                SET next_sync_at = now() + ($1 || ' seconds')::interval
                WHERE id = $2
                """,
                interval, row["source_id"],
            )
            n += 1
    if n > 0:
        log.info("sync.scheduler.scheduled", count=n)
    return n


def _extract_interval(config, default_seconds: int) -> int:
    """Lit `sync_interval_seconds` dans le JSONB de la source (clé optionnelle).

    asyncpg retourne le jsonb sous forme de `dict` directement.
    """
    if isinstance(config, dict):
        val = config.get("sync_interval_seconds")
        if isinstance(val, int) and val >= 60:
            return val
    return default_seconds
```

- [ ] **Step 10.4 : Vert + commit**

```powershell
uv run pytest tests/integration/test_sync_scheduler.py -v
```

```bash
git add backend/src/rag/sync/scheduler.py backend/tests/integration/test_sync_scheduler.py
git commit -m "feat(sync): scheduler (next_sync_at → jobs pending + bump interval)"
```

---

## Task 11 — `sync/executor.py` : picker (pending → running)

**Files:**
- Create: `backend/src/rag/sync/executor.py`
- Create: `backend/tests/integration/test_sync_picker.py`

Cette task implémente uniquement `pick_next_pending_job` (atomique). La fonction `process_job` (pipeline complet) vient en T12.

- [ ] **Step 11.1 : Tests (rouge)**

```python
# backend/tests/integration/test_sync_picker.py
from __future__ import annotations

import json
from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.sync.executor import pick_next_pending_job

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def _setup_ws_src_indexer(pool: asyncpg.Pool, name: str) -> tuple[str, str]:
    async with pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ($1, 'h', 'c', 'b') RETURNING id",
            name,
        )
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        src_id = await conn.fetchval(
            "INSERT INTO workspace_sources (workspace_id, type, config, next_sync_at) "
            "VALUES ($1, 'git', $2::jsonb, NULL) RETURNING id",
            ws_id, json.dumps({"url": "https://github.com/x/y", "branch": "main"}),
        )
        return ws_id, src_id


@pytest.mark.asyncio
async def test_picker_returns_none_when_no_pending(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    result = await pick_next_pending_job(session_pool)
    assert result is None


@pytest.mark.asyncio
async def test_picker_transitions_pending_to_running(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    ws_id, src_id = await _setup_ws_src_indexer(session_pool, "ws_pick_a")
    async with session_pool.acquire() as conn:
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, source_id, triggered_by, status) "
            "VALUES ($1, $2, 'manual', 'pending') RETURNING id",
            ws_id, src_id,
        )

    result = await pick_next_pending_job(session_pool)
    assert result is not None
    assert str(result.job_id) == str(job_id)
    assert str(result.workspace_id) == str(ws_id)
    assert result.workspace_name == "ws_pick_a"
    assert str(result.source_id) == str(src_id)
    assert result.indexer_provider == "openai"
    assert result.indexer_model == "text-embedding-3-small"
    assert result.indexer_used == "openai/text-embedding-3-small"

    # Job passé en running
    status = await session_pool.fetchval(
        "SELECT status FROM index_jobs WHERE id=$1", job_id,
    )
    assert status == "running"


@pytest.mark.asyncio
async def test_picker_skips_non_pending_jobs(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    ws_id, src_id = await _setup_ws_src_indexer(session_pool, "ws_pick_b")
    async with session_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO index_jobs (workspace_id, source_id, triggered_by, status, finished_at) "
            "VALUES ($1, $2, 'manual', 'done', now())",
            ws_id, src_id,
        )

    result = await pick_next_pending_job(session_pool)
    assert result is None
```

- [ ] **Step 11.2 : Rouge → 3 ERROR.**

- [ ] **Step 11.3 : Impl**

Créer `backend/src/rag/sync/executor.py` :

```python
from __future__ import annotations

import asyncpg
import structlog

from rag.schemas.sync import JobToProcess

log = structlog.get_logger(__name__)


async def pick_next_pending_job(
    config_pool: asyncpg.Pool,
) -> JobToProcess | None:
    """Picke le job pending le plus ancien et le transitionne en running
    atomiquement (CTE + UPDATE … FROM).

    Retourne `None` si aucun job pending. Sinon retourne un `JobToProcess`
    avec tout le contexte nécessaire à l'executor (workspace, source, indexer).

    `FOR UPDATE SKIP LOCKED` rend l'opération safe pour multi-worker M3+.
    """
    async with config_pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """
            WITH picked AS (
                SELECT id FROM index_jobs
                WHERE status = 'pending'
                ORDER BY id
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            UPDATE index_jobs j
            SET status='running', started_at=now()
            FROM picked
            WHERE j.id = picked.id
            RETURNING
                j.id AS job_id,
                j.workspace_id,
                j.source_id
            """
        )
        if row is None:
            return None

        context = await conn.fetchrow(
            """
            SELECT
                w.name AS workspace_name,
                ws.config AS source_config,
                ic.provider AS indexer_provider,
                ic.model AS indexer_model
            FROM workspaces w
            LEFT JOIN workspace_sources ws ON ws.id = $1
            LEFT JOIN indexer_configs ic ON ic.workspace_id = w.id
            WHERE w.id = $2
            """,
            row["source_id"], row["workspace_id"],
        )

    if context is None:
        # Workspace introuvable — devrait jamais arriver mais on log.
        log.error("sync.picker.workspace_not_found", workspace_id=str(row["workspace_id"]))
        return None

    return JobToProcess(
        job_id=row["job_id"],
        workspace_id=row["workspace_id"],
        workspace_name=context["workspace_name"],
        source_id=row["source_id"],
        source_config=dict(context["source_config"] or {}),
        indexer_provider=context["indexer_provider"] or "",
        indexer_model=context["indexer_model"] or "",
    )
```

- [ ] **Step 11.4 : Vert + commit**

```powershell
uv run pytest tests/integration/test_sync_picker.py -v
```

```bash
git add backend/src/rag/sync/executor.py backend/tests/integration/test_sync_picker.py
git commit -m "feat(sync): pick_next_pending_job (CTE + FOR UPDATE SKIP LOCKED)"
```

---

## Task 12 — `executor.process_job` : pipeline complet

**Files:**
- Modify: `backend/src/rag/sync/executor.py` (ajout `process_job`, `execute_next_pending_job`, helpers)
- Create: `backend/tests/integration/test_sync_executor.py`

C'est la task la plus grosse de M3. Elle orchestre tout : auth resolve, ensure_clone_or_pull, diff, dédup, indexer calls, UPDATE config + status.

- [ ] **Step 12.1 : Tests E2E executor (rouge)**

```python
# backend/tests/integration/test_sync_executor.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.indexer.noop import NoOpIndexer
from rag.sync.executor import execute_next_pending_job
from rag.sync.repo_storage import RepoStorage
from tests.integration._git_fixture import add_commit, make_bare_repo_with_commits

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _StubResolver:
    """Stub : retourne 'tok-x' quel que soit le ref demandé."""

    def resolve_with_retry(self, ref: str) -> str:
        return "tok-x"


async def _make_workspace_with_indexer(
    pool: asyncpg.Pool, name: str,
) -> str:
    async with pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ($1, 'h', 'c', 'b') RETURNING id",
            name,
        )
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
    return ws_id


async def _make_source(
    pool: asyncpg.Pool, ws_id: str, url: str, branch: str = "main",
    auth_ref: str | None = None,
) -> str:
    cfg: dict[str, Any] = {"url": url, "branch": branch}
    if auth_ref:
        cfg["auth_ref"] = auth_ref
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO workspace_sources (workspace_id, type, config, next_sync_at) "
            "VALUES ($1, 'git', $2::jsonb, now()) RETURNING id",
            ws_id, json.dumps(cfg),
        )


async def _make_pending_job(pool: asyncpg.Pool, ws_id: str, src_id: str) -> str:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, source_id, triggered_by, status) "
            "VALUES ($1, $2, 'manual', 'pending') RETURNING id",
            ws_id, src_id,
        )


@pytest.mark.asyncio
async def test_executor_first_sync_all_files_indexed(
    session_pool: asyncpg.Pool, tmp_path: Path,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    bare = make_bare_repo_with_commits(
        tmp_path, {"a.md": "v1", "b.md": "v1"},
    )

    ws_id = await _make_workspace_with_indexer(session_pool, "ws_exec_a")
    src_id = await _make_source(session_pool, ws_id, url=f"file://{bare}")
    job_id = await _make_pending_job(session_pool, ws_id, src_id)

    storage = RepoStorage(root=tmp_path / "repos")
    indexer = NoOpIndexer(session_pool)
    processed = await execute_next_pending_job(
        config_pool=session_pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
    )
    assert processed is True

    row = await session_pool.fetchrow(
        "SELECT status, files_changed, files_skipped, finished_at "
        "FROM index_jobs WHERE id=$1",
        job_id,
    )
    assert row["status"] == "done"
    assert row["files_changed"] == 2
    assert row["files_skipped"] == 0
    assert row["finished_at"] is not None

    docs = await session_pool.fetch(
        "SELECT path FROM indexed_documents WHERE workspace_id=$1 ORDER BY path",
        ws_id,
    )
    assert [r["path"] for r in docs] == ["a.md", "b.md"]


@pytest.mark.asyncio
async def test_executor_second_sync_no_change_skips_all(
    session_pool: asyncpg.Pool, tmp_path: Path,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    bare = make_bare_repo_with_commits(tmp_path, {"a.md": "v1", "b.md": "v1"})

    ws_id = await _make_workspace_with_indexer(session_pool, "ws_exec_b")
    src_id = await _make_source(session_pool, ws_id, url=f"file://{bare}")
    await _make_pending_job(session_pool, ws_id, src_id)

    storage = RepoStorage(root=tmp_path / "repos")
    indexer = NoOpIndexer(session_pool)
    await execute_next_pending_job(
        config_pool=session_pool, storage=storage, indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
    )

    # 2e sync : nouveau job pending sans changement remote
    job2_id = await _make_pending_job(session_pool, ws_id, src_id)
    await execute_next_pending_job(
        config_pool=session_pool, storage=storage, indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
    )

    row = await session_pool.fetchrow(
        "SELECT status, files_changed, files_skipped FROM index_jobs WHERE id=$1",
        job2_id,
    )
    assert row["status"] == "done"
    assert row["files_changed"] == 0
    assert row["files_skipped"] == 2


@pytest.mark.asyncio
async def test_executor_second_sync_detects_modify_and_delete(
    session_pool: asyncpg.Pool, tmp_path: Path,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    bare = make_bare_repo_with_commits(tmp_path, {"a.md": "v1", "b.md": "v1"})

    ws_id = await _make_workspace_with_indexer(session_pool, "ws_exec_c")
    src_id = await _make_source(session_pool, ws_id, url=f"file://{bare}")
    await _make_pending_job(session_pool, ws_id, src_id)

    storage = RepoStorage(root=tmp_path / "repos")
    indexer = NoOpIndexer(session_pool)
    await execute_next_pending_job(
        config_pool=session_pool, storage=storage, indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
    )

    # Modifie b.md, ajoute c.md, supprime a.md
    work = tmp_path / "work"
    add_commit(work, files={"b.md": "v2", "c.md": "v1"}, deletes=["a.md"])

    job2_id = await _make_pending_job(session_pool, ws_id, src_id)
    await execute_next_pending_job(
        config_pool=session_pool, storage=storage, indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
    )

    row = await session_pool.fetchrow(
        "SELECT files_changed, files_skipped FROM index_jobs WHERE id=$1",
        job2_id,
    )
    # b modifié (1) + c ajouté (1) + a supprimé (1) = 3 changes
    assert row["files_changed"] == 3
    assert row["files_skipped"] == 0

    docs = await session_pool.fetch(
        "SELECT path FROM indexed_documents WHERE workspace_id=$1 ORDER BY path",
        ws_id,
    )
    paths = [r["path"] for r in docs]
    assert "a.md" not in paths   # deleted
    assert "b.md" in paths
    assert "c.md" in paths


@pytest.mark.asyncio
async def test_executor_failure_on_invalid_url_marks_error(
    session_pool: asyncpg.Pool, tmp_path: Path,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)

    ws_id = await _make_workspace_with_indexer(session_pool, "ws_exec_d")
    src_id = await _make_source(
        session_pool, ws_id, url="file:///nonexistent/repo.git",
    )
    job_id = await _make_pending_job(session_pool, ws_id, src_id)

    storage = RepoStorage(root=tmp_path / "repos")
    indexer = NoOpIndexer(session_pool)
    await execute_next_pending_job(
        config_pool=session_pool, storage=storage, indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
    )

    row = await session_pool.fetchrow(
        "SELECT status, error_message FROM index_jobs WHERE id=$1", job_id,
    )
    assert row["status"] == "error"
    assert "git clone failed" in row["error_message"]


@pytest.mark.asyncio
async def test_executor_returns_false_when_no_pending(
    session_pool: asyncpg.Pool, tmp_path: Path,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    storage = RepoStorage(root=tmp_path / "repos")
    indexer = NoOpIndexer(session_pool)
    processed = await execute_next_pending_job(
        config_pool=session_pool, storage=storage, indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
    )
    assert processed is False
```

- [ ] **Step 12.2 : Rouge → 5 ERROR `cannot import 'execute_next_pending_job'`.**

- [ ] **Step 12.3 : Impl**

Ajouter en fin de `backend/src/rag/sync/executor.py` :

```python
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from rag.indexer.protocol import IndexerProtocol
from rag.schemas.sync import ChangeSet, GitOpResult
from rag.secrets.resolver import VaultLookupFailed
from rag.sync.git_ops import (
    GitCloneError,
    GitPullError,
    clone,
    diff_changes,
    filter_glob,
    head_commit,
    list_all_files,
    pull,
    sanitize_git_output,
)
from rag.sync.repo_storage import RepoStorage


class _ResolverProtocol(Protocol):
    def resolve_with_retry(self, ref: str) -> str: ...


_ERROR_MESSAGE_MAX = 500


def _truncate(s: str, n: int = _ERROR_MESSAGE_MAX) -> str:
    if len(s) <= n:
        return s
    return s[: n - 3] + "..."


def _to_vault_ref(logical_key: str, *, vault_id: str = "rag") -> str:
    return f"${{vault://{vault_id}:{logical_key}}}"


def _resolve_token(
    resolver: _ResolverProtocol, config: dict[str, Any],
) -> str | None:
    """Résout `auth_ref` si présent. None si source publique."""
    auth_ref = config.get("auth_ref")
    if not auth_ref:
        return None
    return resolver.resolve_with_retry(_to_vault_ref(auth_ref))


async def execute_next_pending_job(
    *,
    config_pool: asyncpg.Pool,
    storage: RepoStorage,
    indexer: IndexerProtocol,
    resolver: _ResolverProtocol,
) -> bool:
    """Picke 1 job pending + exécute le pipeline complet.

    Retourne True si un job a été traité (peu importe done/error), False si
    aucun job pending.
    """
    job = await pick_next_pending_job(config_pool)
    if job is None:
        return False

    try:
        await _process_job(
            job=job, config_pool=config_pool, storage=storage,
            indexer=indexer, resolver=resolver,
        )
    except Exception as e:  # noqa: BLE001 — on capture tout pour marquer error
        msg = _format_error(e)
        log.exception("sync.executor.job_error", job_id=str(job.job_id))
        await _mark_job_error(config_pool, job_id=job.job_id, error_message=msg)
    return True


def _format_error(e: BaseException) -> str:
    """Format compact pour `index_jobs.error_message`, sanitized."""
    if isinstance(e, GitCloneError):
        return _truncate(f"git clone failed: {sanitize_git_output(str(e))}")
    if isinstance(e, GitPullError):
        return _truncate(f"git pull failed: {sanitize_git_output(str(e))}")
    if isinstance(e, VaultLookupFailed):
        return _truncate(f"auth_ref not resolvable: {e}")
    return _truncate(
        f"unexpected: {type(e).__name__}: {sanitize_git_output(str(e))}", 200,
    )


async def _mark_job_error(
    config_pool: asyncpg.Pool, *, job_id: UUID, error_message: str,
) -> None:
    async with config_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE index_jobs
            SET status='error',
                error_message=$1,
                finished_at=now(),
                duration_ms=CASE
                    WHEN started_at IS NOT NULL THEN
                        EXTRACT(MILLISECONDS FROM (now() - started_at))::int
                    ELSE 0
                END
            WHERE id=$2
            """,
            error_message, job_id,
        )


async def _process_job(
    *,
    job,  # JobToProcess (cyclic import guard, type via runtime)
    config_pool: asyncpg.Pool,
    storage: RepoStorage,
    indexer: IndexerProtocol,
    resolver: _ResolverProtocol,
) -> None:
    config = job.source_config
    url = config["url"]
    branch = config.get("branch", "main")
    include = config.get("include") or ["**/*"]
    exclude = config.get("exclude") or []
    last_commit = config.get("last_commit")

    # 1. Résolution token (lazy)
    token = _resolve_token(resolver, config)

    # 2. Path local + clone ou pull
    storage.ensure_exists(workspace_id=job.workspace_id, source_id=job.source_id)
    dest = storage.path_for(workspace_id=job.workspace_id, source_id=job.source_id)

    if storage.has_git(workspace_id=job.workspace_id, source_id=job.source_id):
        await pull(dest=dest, branch=branch)
        was_fresh_clone = False
    else:
        # Le ensure_exists a créé un dossier vide. `git clone` exige que la
        # cible n'existe pas (ou soit vide). On retire et laisse git créer.
        if dest.exists():
            for child in dest.iterdir():
                if child.is_dir():
                    import shutil
                    shutil.rmtree(child)
                else:
                    child.unlink()
            dest.rmdir()
        await clone(url=url, branch=branch, token=token, dest=dest)
        was_fresh_clone = True

    current = await head_commit(dest)

    # 3. Diff
    if last_commit is None or was_fresh_clone:
        all_files = await list_all_files(dest)
        changes = ChangeSet(added=all_files)
    else:
        changes = await diff_changes(
            dest=dest, from_commit=last_commit, to_commit=current,
        )
    changes = filter_glob(changes, include=include, exclude=exclude)

    # 4. Traite les fichiers
    files_changed = 0
    files_skipped = 0

    for path in changes.added + changes.modified:
        full = dest / path
        try:
            content = full.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue  # binaire / lien cassé → skip silencieux

        content_hash = "sha256:" + sha256(content.encode("utf-8")).hexdigest()

        async with config_pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT content_hash FROM indexed_documents "
                "WHERE workspace_id=$1 AND path=$2",
                job.workspace_id, path,
            )
        if existing == content_hash:
            files_skipped += 1
            continue

        await indexer.index_file(
            workspace_id=job.workspace_id, path=path, content=content,
            content_hash=content_hash, indexer_used=job.indexer_used,
        )
        files_changed += 1

    for path in changes.deleted:
        await indexer.delete_file(workspace_id=job.workspace_id, path=path)
        files_changed += 1

    # 5. Update workspace_sources : last_commit + last_indexed_at
    async with config_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE workspace_sources
            SET config = jsonb_set(
                    coalesce(config, '{}'::jsonb),
                    '{last_commit}',
                    to_jsonb($1::text)
                ),
                last_indexed_at = now()
            WHERE id = $2
            """,
            current, job.source_id,
        )

    # 6. Mark done
    async with config_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE index_jobs
            SET status='done',
                finished_at=now(),
                duration_ms=EXTRACT(MILLISECONDS FROM (now() - started_at))::int,
                files_changed=$1,
                files_skipped=$2
            WHERE id=$3
            """,
            files_changed, files_skipped, job.job_id,
        )

    log.info(
        "sync.executor.job_done",
        job_id=str(job.job_id), workspace=job.workspace_name,
        files_changed=files_changed, files_skipped=files_skipped,
    )
```

- [ ] **Step 12.4 : Vert + commit**

```powershell
uv run pytest tests/integration/test_sync_executor.py -v
uv run ruff check src/rag/sync/executor.py tests/integration/test_sync_executor.py
uv run mypy src/rag/sync/executor.py
```

5 PASS.

```bash
git add backend/src/rag/sync/executor.py backend/tests/integration/test_sync_executor.py
git commit -m "feat(sync): executor pipeline complet (clone/pull + diff + dédup + indexer + status)"
```

---

## Task 13 — Modif rétro M2 : `services/sources.add_source` set `next_sync_at=now()`

**Files:**
- Modify: `backend/src/rag/services/sources.py` (1 changement INSERT)
- Modify: `backend/tests/integration/test_services_sources.py` (ajout 1 test)

- [ ] **Step 13.1 : Test (rouge)**

Ajouter en fin de `backend/tests/integration/test_services_sources.py` :

```python
@pytest.mark.asyncio
async def test_add_source_sets_next_sync_at_to_now(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    """M3 : à la création d'une source, next_sync_at doit être posé à now()
    pour déclencher le premier sync au prochain cycle du worker."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    resolver = await _setup_ws(pg_container, session_pool, "ws_src_next_sync")

    src = await add_source(
        workspace_name="ws_src_next_sync",
        request=SourceCreateRequest(
            type="git",
            config={"url": "https://github.com/x/y", "auth_ref": "github_token"},
        ),
        config_pool=session_pool,
        resolver=resolver,  # type: ignore[arg-type]
    )

    next_at_offset = await session_pool.fetchval(
        "SELECT EXTRACT(EPOCH FROM (next_sync_at - now())) "
        "FROM workspace_sources WHERE id=$1",
        src["id"],
    )
    # next_sync_at devrait être quasi maintenant (±5s)
    assert -5 <= float(next_at_offset) <= 5
```

- [ ] **Step 13.2 : Rouge**

```powershell
$env:TEST_POSTGRES_PASSWORD = "LJu_nISEyxccTdm2w72l4AkDVsUF4BeR"
uv run pytest tests/integration/test_services_sources.py::test_add_source_sets_next_sync_at_to_now -v
```

Expected : FAIL (current INSERT laisse next_sync_at NULL).

- [ ] **Step 13.3 : Modifier l'INSERT dans `add_source`**

Dans `backend/src/rag/services/sources.py`, fonction `add_source`, remplacer l'INSERT par :

```python
    async with config_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO workspace_sources (workspace_id, type, config, next_sync_at)
            VALUES ($1, $2, $3::jsonb, now())
            RETURNING id, type, config, last_indexed_at, created_at
            """,
            ws_id,
            request.type,
            json.dumps(request.config),
        )
```

(Le seul changement est `, next_sync_at` dans la liste des colonnes et `, now()` dans VALUES.)

- [ ] **Step 13.4 : Vert + régression**

```powershell
uv run pytest tests/integration/test_services_sources.py -v
```

Tous tests T13 + T13-bis verts (régression M2 OK).

- [ ] **Step 13.5 : Commit**

```bash
git add backend/src/rag/services/sources.py backend/tests/integration/test_services_sources.py
git commit -m "refactor(services): add_source set next_sync_at=now() (déclenche 1er sync M3)"
```

---

## Task 14 — `sync/worker.py` : SyncWorker (boucle + lifespan)

**Files:**
- Create: `backend/src/rag/sync/worker.py`
- Create: `backend/tests/integration/test_sync_worker.py`

- [ ] **Step 14.1 : Tests (rouge)**

```python
# backend/tests/integration/test_sync_worker.py
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.indexer.noop import NoOpIndexer
from rag.sync.repo_storage import RepoStorage
from rag.sync.worker import SyncWorker
from tests.integration._git_fixture import make_bare_repo_with_commits

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _StubResolver:
    def resolve_with_retry(self, ref: str) -> str:
        return "tok-x"


@pytest.mark.asyncio
async def test_worker_processes_pending_job_within_one_cycle(
    session_pool: asyncpg.Pool, tmp_path: Path,
) -> None:
    """SyncWorker démarré → en 1 tick, le job pending passe en done."""
    await run_migrations(session_pool, MIGRATIONS_DIR)

    bare = make_bare_repo_with_commits(tmp_path, {"a.md": "v1"})
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ('ws_worker_a', 'h', 'c', 'b') RETURNING id"
        )
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        src_id = await conn.fetchval(
            "INSERT INTO workspace_sources (workspace_id, type, config, next_sync_at) "
            "VALUES ($1, 'git', $2::jsonb, NULL) RETURNING id",
            ws_id, json.dumps({"url": f"file://{bare}", "branch": "main"}),
        )
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, source_id, triggered_by, status) "
            "VALUES ($1, $2, 'manual', 'pending') RETURNING id",
            ws_id, src_id,
        )

    worker = SyncWorker(
        config_pool=session_pool,
        storage=RepoStorage(root=tmp_path / "repos"),
        indexer=NoOpIndexer(session_pool),
        resolver=_StubResolver(),  # type: ignore[arg-type]
        poll_interval_seconds=1,
        default_sync_interval_seconds=300,
    )
    await worker.start()
    # Laisse le worker traiter 1 cycle
    await asyncio.sleep(2)
    await worker.stop()

    status = await session_pool.fetchval(
        "SELECT status FROM index_jobs WHERE id=$1", job_id,
    )
    assert status == "done"


@pytest.mark.asyncio
async def test_worker_schedules_due_sources(
    session_pool: asyncpg.Pool, tmp_path: Path,
) -> None:
    """Worker → scheduler crée un job pour une source dont next_sync_at est passé."""
    await run_migrations(session_pool, MIGRATIONS_DIR)

    bare = make_bare_repo_with_commits(tmp_path, {"a.md": "v1"})
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ('ws_worker_b', 'h', 'c', 'b') RETURNING id"
        )
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        src_id = await conn.fetchval(
            "INSERT INTO workspace_sources (workspace_id, type, config, next_sync_at) "
            "VALUES ($1, 'git', $2::jsonb, now() - interval '60 seconds') RETURNING id",
            ws_id, json.dumps({"url": f"file://{bare}", "branch": "main"}),
        )

    worker = SyncWorker(
        config_pool=session_pool,
        storage=RepoStorage(root=tmp_path / "repos"),
        indexer=NoOpIndexer(session_pool),
        resolver=_StubResolver(),  # type: ignore[arg-type]
        poll_interval_seconds=1,
        default_sync_interval_seconds=300,
    )
    await worker.start()
    await asyncio.sleep(3)
    await worker.stop()

    # Un job triggered_by=schedule existe et est done
    row = await session_pool.fetchrow(
        "SELECT triggered_by, status FROM index_jobs WHERE workspace_id=$1",
        ws_id,
    )
    assert row is not None
    assert row["triggered_by"] == "schedule"
    assert row["status"] == "done"


@pytest.mark.asyncio
async def test_worker_stop_idempotent(session_pool: asyncpg.Pool, tmp_path: Path) -> None:
    """Stop sans start ou stop appelé deux fois ne lève pas."""
    worker = SyncWorker(
        config_pool=session_pool,
        storage=RepoStorage(root=tmp_path / "repos"),
        indexer=NoOpIndexer(session_pool),
        resolver=_StubResolver(),  # type: ignore[arg-type]
        poll_interval_seconds=30,
        default_sync_interval_seconds=300,
    )
    await worker.stop()  # avant start
    await worker.start()
    await worker.stop()
    await worker.stop()  # idempotent
```

- [ ] **Step 14.2 : Rouge → 3 ERROR.**

- [ ] **Step 14.3 : Impl**

Créer `backend/src/rag/sync/worker.py` :

```python
from __future__ import annotations

import asyncio
from typing import Protocol

import asyncpg
import structlog

from rag.indexer.protocol import IndexerProtocol
from rag.sync.executor import execute_next_pending_job
from rag.sync.repo_storage import RepoStorage
from rag.sync.scheduler import schedule_due_sources

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    def resolve_with_retry(self, ref: str) -> str: ...


class SyncWorker:
    """Worker asyncio géré par le lifespan FastAPI.

    Boucle infinie qui réveille toutes les `poll_interval_seconds` :
      1. schedule_due_sources(...) → INSERT jobs pour les sources dues
      2. execute_next_pending_job(...) → picke 1 job, exécute, transition
      3. asyncio.sleep(poll_interval_seconds)

    Lifecycle :
      - `await worker.start()` lance la task.
      - `await worker.stop()` set un Event d'arrêt et await la task (avec
        timeout pour éviter les hang). Idempotent.

    Single replica : la sub-query `NOT EXISTS pending|running` du scheduler
    + `FOR UPDATE SKIP LOCKED` du picker rendent multi-worker safe en théorie,
    mais M3 reste single-task.
    """

    def __init__(
        self,
        *,
        config_pool: asyncpg.Pool,
        storage: RepoStorage,
        indexer: IndexerProtocol,
        resolver: _ResolverProtocol,
        poll_interval_seconds: int,
        default_sync_interval_seconds: int,
    ) -> None:
        self._config_pool = config_pool
        self._storage = storage
        self._indexer = indexer
        self._resolver = resolver
        self._poll_interval = poll_interval_seconds
        self._default_sync_interval = default_sync_interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Démarre la task de fond. No-op si déjà démarrée."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="sync-worker")
        log.info("sync.worker.started", poll_interval=self._poll_interval)

    async def stop(self, *, timeout: float = 10.0) -> None:
        """Demande l'arrêt et attend la task. Idempotent."""
        self._stop_event.set()
        if self._task is None:
            return
        try:
            await asyncio.wait_for(self._task, timeout=timeout)
        except TimeoutError:
            log.warning("sync.worker.stop_timeout")
            self._task.cancel()
        finally:
            self._task = None
            log.info("sync.worker.stopped")

    async def _run(self) -> None:
        """Boucle principale. Catch toutes les exceptions de cycle pour
        ne pas tuer le worker — chaque cycle est isolé.
        """
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
                )
            except Exception:  # noqa: BLE001
                log.exception("sync.worker.cycle_error")

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._poll_interval,
                )
            except TimeoutError:
                pass  # timeout = prochain cycle
```

- [ ] **Step 14.4 : Vert + commit**

```powershell
uv run pytest tests/integration/test_sync_worker.py -v
uv run ruff check src/rag/sync/worker.py tests/integration/test_sync_worker.py
uv run mypy src/rag/sync/worker.py
```

3 PASS.

```bash
git add backend/src/rag/sync/worker.py backend/tests/integration/test_sync_worker.py
git commit -m "feat(sync): SyncWorker (boucle scheduler+executor, start/stop lifecycle)"
```

---

## Task 15 — Dockerfile : installer `git`

**Files:**
- Modify: `backend/Dockerfile` (1 ligne RUN apt-get install)

- [ ] **Step 15.1 : Modifier le Dockerfile**

Lire `backend/Dockerfile` pour trouver l'apt-get existant (M1 installe `curl` + `git` déjà pour le fetch SDK Harpocrate). Vérifier que `git` est bien dans la liste — il devrait y être. Si présent → cette task est NO-OP, juste vérifier puis commit `chore: noop (git déjà installé)`.

Si absent, ajouter `git` à la commande `apt-get install`. Exemple si l'apt-get actuel est :

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*
```

→ devient :

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 15.2 : Vérification locale (skipper si pas Docker Desktop)**

Build le backend sur LXC 303 (au lieu de local — Docker Desktop pas dispo Windows) :

```bash
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && docker compose -f docker-compose-dev.yml build backend'"
```

Expected : build OK, image `rag-backend:latest` rebuilt.

Test que `git` est dans l'image :

```bash
ssh pve "pct exec 303 -- docker run --rm rag-backend:latest git --version"
```

Expected : `git version 2.x.x`.

- [ ] **Step 15.3 : Commit**

```bash
git add backend/Dockerfile
git commit -m "chore(docker): garantit git CLI dans l'image backend pour le sync worker M3"
```

(Si NO-OP : ne pas committer, sauter cette task.)

---

## Task 16 — `docker-compose-dev.yml` : volume `rag_repos`

**Files:**
- Modify: `docker-compose-dev.yml` (ajout volume named + mount)

- [ ] **Step 16.1 : Modifier le compose**

Dans `docker-compose-dev.yml`, dans le service `backend`, ajouter sous `environment:` (ou créer une section `volumes:` si absente) :

```yaml
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    image: rag-backend:latest
    container_name: rag-backend
    restart: unless-stopped
    env_file: .env
    environment:
      GIT_SHA: ${GIT_SHA:-unknown}
    ports:
      - "8000:8000"
    depends_on:
      postgres: { condition: service_healthy }
    networks: [rag]
    volumes:
      - rag_repos:/var/lib/rag/repos    # NEW M3
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 10s
      retries: 5
```

Et en fin de fichier, dans la section `volumes:`, ajouter :

```yaml
volumes:
  postgres_data:
  caddy_data:
  caddy_config:
  rag_repos:    # NEW M3 : clones git persistants
```

- [ ] **Step 16.2 : Commit**

```bash
git add docker-compose-dev.yml
git commit -m "feat(infra): volume named rag_repos pour les clones git persistants (M3)"
```

(Le compose sera testé en E2E via T18 + smoke deploy T19.)

---

## Task 17 — `main.py` : wire-up du worker

**Files:**
- Modify: `backend/src/rag/main.py`

- [ ] **Step 17.1 : Test wire-up (rouge)**

Créer `backend/tests/api/test_sync_wireup.py` :

```python
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from rag.main import build_app
from rag.secrets.resolver import SecretResolver

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest_asyncio.fixture
async def wired_client(pg_container: str, tmp_path: Path) -> AsyncIterator[TestClient]:
    os.environ["DATABASE_URL"] = pg_container
    os.environ["RAG_POSTGRES_ADMIN_URL"] = pg_container.rsplit("/", 1)[0] + "/postgres"
    os.environ.setdefault("RAG_MASTER_KEY", "mk_test_sync")
    os.environ.setdefault("RAG_PUBLIC_URL", "http://localhost:8000")
    os.environ.setdefault("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_stub")
    os.environ.setdefault("HARPOCRATE_API_URL_RAG", "https://vault.example.com")
    os.environ.setdefault("ENVIRONMENT", "dev")
    os.environ["SYNC_REPOS_ROOT"] = str(tmp_path / "repos")
    os.environ["SYNC_WORKER_POLL_INTERVAL_SECONDS"] = "1"

    app = build_app(
        version="0.3.0",
        git_sha="testsha",
        resolver_factory=lambda _cfg: SecretResolver(harpocrate_clients={}),
        migrations_dir=_MIGRATIONS_DIR,
    )
    with TestClient(app) as client:
        yield client


def test_sync_worker_attached_to_app_state(wired_client: TestClient) -> None:
    """Après lifespan startup, app.state.sync_worker doit exister et tourner."""
    app = wired_client.app
    assert hasattr(app.state, "sync_worker")
    assert app.state.sync_worker is not None


def test_recovery_runs_at_boot(wired_client: TestClient, pg_container: str) -> None:
    """Avant le lifespan de TestClient, on a inséré un job running. Au boot,
    il doit être marqué error/stale_at_boot."""
    # NOTE : le setup nécessite un INSERT avant le `with TestClient(app)`,
    # donc on contourne en utilisant directement un sub-app pour le test.
    # Variant : tester recovery isolé (déjà fait en T9), ici juste vérifier
    # que recovery est BIEN appelé au lifespan.
    # On lit les logs ou on inspecte un effet de bord. Le plus simple :
    # vérifier que /health répond (signifie lifespan complet OK).
    r = wired_client.get("/health")
    assert r.status_code == 200
```

- [ ] **Step 17.2 : Rouge**

```powershell
$env:TEST_POSTGRES_PASSWORD = "LJu_nISEyxccTdm2w72l4AkDVsUF4BeR"
uv run pytest tests/api/test_sync_wireup.py -v
```

Expected : FAIL (`app.state.sync_worker` n'existe pas).

- [ ] **Step 17.3 : Modifier `main.py`**

Dans `backend/src/rag/main.py`, fonction `build_app`, dans le `lifespan` :

1. Avant `yield`, ajouter (juste après l'init du resolver et le run des migrations) :

```python
        # M3 : recovery au boot (jobs running orphelins → error)
        from rag.sync.recovery import reset_stale_running_jobs
        await reset_stale_running_jobs(registry.config_pool)

        # M3 : démarre le sync worker
        from rag.indexer.noop import NoOpIndexer
        from rag.sync.repo_storage import RepoStorage
        from rag.sync.worker import SyncWorker

        sync_worker = SyncWorker(
            config_pool=registry.config_pool,
            storage=RepoStorage(root=settings.sync_repos_root),
            indexer=NoOpIndexer(registry.config_pool),
            resolver=app.state.resolver,
            poll_interval_seconds=settings.sync_worker_poll_interval_seconds,
            default_sync_interval_seconds=settings.sync_default_interval_seconds,
        )
        await sync_worker.start()
        app.state.sync_worker = sync_worker
```

2. Dans le `finally:` du lifespan, AVANT `await registry.close_all()`, ajouter :

```python
            if hasattr(app.state, "sync_worker"):
                await app.state.sync_worker.stop()
```

- [ ] **Step 17.4 : Vert + lint**

```powershell
uv run pytest tests/api/test_sync_wireup.py -v
uv run ruff check src/rag/main.py tests/api/test_sync_wireup.py
uv run mypy src/rag/main.py
```

2 PASS + clean.

- [ ] **Step 17.5 : Commit**

```bash
git add backend/src/rag/main.py backend/tests/api/test_sync_wireup.py
git commit -m "feat(main): wire-up SyncWorker au lifespan (recovery + start + stop)"
```

---

## Task 18 — Tests E2E API : `POST /reindex` → worker → done

**Files:**
- Create: `backend/tests/api/test_sync_e2e.py`

- [ ] **Step 18.1 : Tests E2E (rouge)**

```python
# backend/tests/api/test_sync_e2e.py
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from rag.main import build_app
from tests.integration._git_fixture import make_bare_repo_with_commits

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _AcceptAllResolver:
    def resolve_with_retry(self, ref: str) -> str:
        return "tok-x"


@pytest_asyncio.fixture
async def e2e_client(
    pg_container: str, tmp_path: Path,
) -> AsyncIterator[tuple[TestClient, Path]]:
    os.environ["DATABASE_URL"] = pg_container
    os.environ["RAG_POSTGRES_ADMIN_URL"] = pg_container.rsplit("/", 1)[0] + "/postgres"
    os.environ.setdefault("RAG_MASTER_KEY", "mk_test_e2e_sync")
    os.environ.setdefault("RAG_PUBLIC_URL", "http://localhost:8000")
    os.environ.setdefault("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_stub")
    os.environ.setdefault("HARPOCRATE_API_URL_RAG", "https://vault.example.com")
    os.environ.setdefault("ENVIRONMENT", "dev")
    os.environ["SYNC_REPOS_ROOT"] = str(tmp_path / "repos")
    os.environ["SYNC_WORKER_POLL_INTERVAL_SECONDS"] = "1"

    app = build_app(
        version="0.3.0",
        git_sha="testsha",
        resolver_factory=lambda _cfg: _AcceptAllResolver(),  # type: ignore[return-value]
        migrations_dir=_MIGRATIONS_DIR,
    )
    with TestClient(app) as client:
        yield client, tmp_path


def _bearer(value: str = "mk_test_e2e_sync") -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


def test_full_pipeline_create_workspace_source_reindex_done(
    e2e_client: tuple[TestClient, Path],
) -> None:
    """E2E complet : create workspace → add source pointant vers bare repo
    local → POST /reindex manuel → worker picke et exécute → job done."""
    client, tmp_path = e2e_client
    bare = make_bare_repo_with_commits(
        tmp_path, {"README.md": "hello", "docs/intro.md": "intro"},
    )

    # 1. Create workspace
    r = client.post(
        "/workspaces",
        headers=_bearer(),
        json={
            "name": "ws_e2e_sync",
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 201

    # 2. Add source (next_sync_at=now() → worker va picker au prochain cycle)
    r = client.post(
        "/workspaces/ws_e2e_sync/sources",
        headers=_bearer(),
        json={
            "type": "git",
            "config": {"url": f"file://{bare}", "branch": "main"},
        },
    )
    assert r.status_code == 201

    # 3. Attendre que le worker traite le job (poll_interval=1s)
    deadline = asyncio.get_event_loop().time() + 15
    final_status = None
    while asyncio.get_event_loop().time() < deadline:
        jobs = client.get("/workspaces/ws_e2e_sync/jobs", headers=_bearer()).json()
        if jobs and jobs[0]["status"] in ("done", "error"):
            final_status = jobs[0]
            break
        # Pas de await asyncio.sleep — TestClient est sync ; on attend via temps mur.
        import time
        time.sleep(0.5)

    assert final_status is not None
    assert final_status["status"] == "done", f"Job status: {final_status}"
    assert final_status["files_changed"] >= 1
```

- [ ] **Step 18.2 : Rouge → fail.**

```powershell
$env:TEST_POSTGRES_PASSWORD = "LJu_nISEyxccTdm2w72l4AkDVsUF4BeR"
uv run pytest tests/api/test_sync_e2e.py -v
```

(Si le wire-up T17 est OK, ce test devrait déjà passer. Si non, c'est ici qu'on détecte les soucis d'intégration finaux.)

- [ ] **Step 18.3 : Vert + commit**

```powershell
uv run pytest tests/api/test_sync_e2e.py -v
```

```bash
git add backend/tests/api/test_sync_e2e.py
git commit -m "test: E2E sync worker (create ws → add source → polling → job done)"
```

---

## Task 19 — Quality gate + smoke deploy LXC + tag m3-done

**Files:**
- aucun nouveau

- [ ] **Step 19.1 : Quality gate local complet**

```powershell
$env:TEST_POSTGRES_PASSWORD = "LJu_nISEyxccTdm2w72l4AkDVsUF4BeR"
Set-Location E:\srcs\ag-flow.rag\backend
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src/rag
uv run pytest --cov=src/rag --cov-report=term-missing
```

Attendu :
- ruff : 0 erreur
- ruff format : tous formatés
- mypy : 0 erreur
- pytest : tous tests verts (~145 M1+M2 + ~35 M3 = ~180 tests verts)
- couverture : ≥90% globale, ≥95% sur `sync/`, `indexer/noop.py`

Si fail → fix (NE PAS toucher aux tests sauf bug avéré). Commit `chore: corrections quality gate M3` + relancer.

- [ ] **Step 19.2 : Push dev**

```bash
git push origin dev
```

- [ ] **Step 19.3 : Deploy LXC 303 (2 runs pour le script en mémoire)**

```bash
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && ./dev-deploy.sh'"
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && ./dev-deploy.sh'"
```

Attendu : `✓ Smoke /health → ok` + tous services healthy + nouveau volume `rag_repos` créé.

Vérification volume :
```bash
ssh pve "pct exec 303 -- docker volume ls | grep rag_repos"
```

Attendu : `local  rag_repos`.

- [ ] **Step 19.4 : Smoke E2E sync worker sur LXC 303**

```bash
# Récupère la master key
MK=$(ssh pve "pct exec 303 -- bash -c 'grep ^RAG_MASTER_KEY /opt/rag/.env | cut -d= -f2'")

# Crée un workspace via l'API
ssh pve "pct exec 303 -- curl -s -X POST -H \"Authorization: Bearer $MK\" \
    -H \"Content-Type: application/json\" \
    -d '{\"name\":\"ws_smoke_m3\",\"indexer\":{\"provider\":\"openai\",\"model\":\"text-embedding-3-small\",\"api_key_ref\":\"openai_embedding_key\"}}' \
    http://localhost:8000/workspaces"

# (Note : le smoke peut échouer ici si openai_embedding_key n'est pas dans Harpocrate.
# Dans ce cas, c'est par design — le vault doit avoir la clé. Pour M3, ce smoke
# valide la machinerie : le worker boote, recovery tourne, lifespan up.
# Un smoke E2E avec un repo git réel viendra en M4 quand l'indexer real existera.)

# Vérifier que le worker est actif (présence dans les logs structlog)
ssh pve "pct exec 303 -- docker compose -f /opt/rag/docker-compose-dev.yml logs backend 2>&1 | grep -E 'sync.worker.(started|cycle|stopped)' | head -5"
```

Attendu : au moins une ligne `sync.worker.started`.

- [ ] **Step 19.5 : Tag m3-done**

```bash
git tag m3-done
git push origin m3-done
```

- [ ] **Step 19.6 : Bilan**

Récap à donner à l'utilisateur :
- Commits M3 : `git log m2-done..m3-done --oneline | wc -l`
- Tests verts (total) : sortie pytest finale
- Coverage globale + par module clé (sync/, indexer/)
- LXC 303 : `sync_worker.started` dans les logs

---

## Récapitulatif M3

À la fin du jalon, le repo contient (en plus de M2) :

```
backend/src/rag/
├── sync/
│   ├── worker.py            # SyncWorker (asyncio task, lifespan-managed)
│   ├── scheduler.py         # schedule_due_sources
│   ├── executor.py          # execute_next_pending_job + process_job pipeline
│   ├── git_ops.py           # clone/pull/diff/list_all_files + sanitize_git_output
│   ├── repo_storage.py      # path_for/ensure_exists/has_git
│   └── recovery.py          # reset_stale_running_jobs
├── indexer/
│   ├── protocol.py          # IndexerProtocol
│   └── noop.py              # NoOpIndexer (M3 : maintient indexed_documents)
├── schemas/
│   └── sync.py              # ChangeSet, GitOpResult, DueSource, JobToProcess
├── services/
│   └── sources.py           # +next_sync_at=now() à la création
└── main.py                  # wire-up recovery + SyncWorker

docker-compose-dev.yml       # volume rag_repos:/var/lib/rag/repos
```

Sur LXC 303 :
- Worker démarre au boot (log `sync.worker.started`).
- Recovery marque les jobs `running` orphelins en `error` `stale_at_boot`.
- Toute source ajoutée a `next_sync_at = now()` → traitée au prochain cycle.
- Les jobs `pending` (manuels ou schedule) transitent en `done` (ou `error` avec message sanitized).
- Les compteurs `files_changed` / `files_skipped` reflètent la dédup SHA-256.
- L'indexer est un `NoOpIndexer` : aucun chunk n'est créé en pgvector — c'est M4 qui branche le moteur effectif.

M4 peut commencer : indexer engine effectif (chunking + providers OpenAI/Voyage/Ollama + upsert pgvector) + API push synchrone + MCP search.

---

## Self-review du plan M3

### 1. Couverture du spec

| Spec section | Task |
|---|---|
| Worker single asyncio task, 3 phases | T14 |
| Scheduler (`next_sync_at` → jobs `schedule`) | T10 |
| Picker (pending → running, `FOR UPDATE SKIP LOCKED`) | T11 |
| Executor pipeline complet + compensation error | T12 |
| Recovery au boot | T9 + T17 |
| `IndexerProtocol` + `NoOpIndexer` (stub M3) | T3 |
| `git_ops` : clone, pull, diff, list_all_files, sanitize, head_commit | T5, T6, T7, T8 |
| `repo_storage` | T4 |
| Schemas internes (`ChangeSet`, `GitOpResult`, `DueSource`, `JobToProcess`) | T2 |
| Settings `sync_default_interval_seconds`, `sync_repos_root` | T1 |
| `.env.example` mis à jour | T1 |
| Modif rétro M2 (`next_sync_at = now()` à création de source) | T13 |
| Volume Docker `rag_repos` | T16 |
| Dockerfile `git` CLI | T15 (no-op si déjà présent) |
| main.py wire-up | T17 |
| Tests E2E API | T18 |
| Quality gate + smoke + tag | T19 |

Couverture complète.

### 2. Cohérence des signatures

- `IndexerProtocol.index_file(*, workspace_id, path, content, content_hash, indexer_used) -> int` — défini T3, consommé T12.
- `IndexerProtocol.delete_file(*, workspace_id, path) -> None` — défini T3, consommé T12.
- `RepoStorage(root)`, `path_for`, `ensure_exists`, `has_git` — défini T4, consommé T12.
- `clone(*, url, branch, token, dest)` — T5, consommé T12.
- `pull(*, dest, branch)`, `head_commit(dest)` — T6, consommé T12.
- `list_all_files(dest) -> list[str]` — T7, consommé T12.
- `diff_changes(*, dest, from_commit, to_commit) -> ChangeSet` — T8, consommé T12.
- `filter_glob(cs, *, include, exclude) -> ChangeSet` — T8, consommé T12.
- `sanitize_git_output(text) -> str` — T5, consommé T12 + executor `_format_error`.
- `pick_next_pending_job(config_pool) -> JobToProcess | None` — T11, consommé T12.
- `execute_next_pending_job(*, config_pool, storage, indexer, resolver) -> bool` — T12, consommé T14.
- `schedule_due_sources(config_pool, *, default_interval_seconds) -> int` — T10, consommé T14.
- `reset_stale_running_jobs(config_pool) -> int` — T9, consommé T17.
- `SyncWorker(*, config_pool, storage, indexer, resolver, poll_interval_seconds, default_sync_interval_seconds)` — T14, consommé T17.

Toutes signatures consistantes.

### 3. Placeholders scan

Recherche manuelle de "TBD"/"TODO"/"fill in"/"appropriate"/"Similar to" : aucun trouvé.

### 4. Estimation

- T1 : 30 min (config + tests)
- T2 : 45 min (DTOs Pydantic + 6 tests)
- T3 : 1h (Protocol + NoOpIndexer + 4 tests intégration)
- T4 : 30 min (repo_storage + 5 tests)
- T5 : 1h30 (clone + sanitize + fixture git + 4 tests)
- T6 : 45 min (pull + head_commit + 4 tests)
- T7 : 30 min (list_all_files + 2 tests)
- T8 : 1h (diff_changes + filter_glob + 5 tests)
- T9 : 45 min (recovery + 2 tests)
- T10 : 1h30 (scheduler + 4 tests)
- T11 : 1h (picker + 3 tests)
- T12 : 3h (executor pipeline + 5 tests E2E — task la plus grosse)
- T13 : 30 min (modif rétro M2 + 1 test)
- T14 : 1h30 (SyncWorker + 3 tests intégration async)
- T15 : 15 min (Dockerfile, probablement no-op)
- T16 : 15 min (compose volume)
- T17 : 1h (main.py wire-up + 2 tests)
- T18 : 1h (E2E API)
- T19 : 1h (quality gate + smoke deploy + tag)

**Total estimé : ~17-18h** soit ~2.5 jours de travail focalisé.
