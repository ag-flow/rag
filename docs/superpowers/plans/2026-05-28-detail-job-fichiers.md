# Détail d'un job au clic (liste des fichiers traités) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre tous les jobs d'indexation cliquables pour afficher, au clic, les fichiers réellement traités (ajoutés/modifiés/supprimés) plus les métadonnées du job.

**Architecture:** Nouvelle table `index_job_files` (migration 017) ; l'executor collecte les chemins traités avec leur type et les persiste en batch au passage `done` ; un endpoint lazy `GET /workspaces/{name}/jobs/{job_id}/files` ; côté frontend un `JobDetailPanel` chargé à la demande quand une ligne est dépliée.

**Tech Stack:** Python 3.12 + asyncpg + structlog + pytest (backend) ; React 18 + TS strict + TanStack Query + Vitest (frontend). Spec : `docs/superpowers/specs/2026-05-28-detail-job-fichiers-design.md`.

**Branche de travail :** `dev` (toujours).

**Contraintes d'environnement local :**
- Les tests d'intégration (`tests/integration/`) **skippent** sans Postgres (`TEST_POSTGRES_PASSWORD`). Valider localement via `--collect-only` + non-régression unit ; validation réelle sur l'infra.
- Tests frontend : lancer **fichier par fichier** (`npx vitest run <path>`), jamais la suite complète (OOM/24 min). Stabiliser tout mock renvoyant un objet via `vi.hoisted` (réf. stable) sous peine d'OOM par boucle de re-render.

**Patterns de référence (existants, ne pas réécrire) :**
- `backend/tests/integration/test_sync_executor.py` : helpers `_make_workspace_with_indexer`, `_make_source`, `_make_pending_job`, `NoOpIndexer`, `RepoStorage`, `execute_next_pending_job`, `_StubResolver`, `_StubClientProvider`, fixture git `make_bare_repo_with_commits` / `add_commit`.
- `backend/src/rag/services/jobs.py` : `list_jobs`, `_job_to_dict`, helpers `fetch_one`/`fetch_all`, `WorkspaceNotFound`.
- `backend/src/rag/api/errors.py` : base `AdminError` (`http_status`, `to_payload`).
- `backend/src/rag/api/admin.py` : endpoints, `_config_pool(request)`, imports retardés des services.
- `frontend/src/lib/workspaces.ts` : `listJobs: (name) => api.get<Job[]>(`${BASE}/${name}/jobs`)`.
- `frontend/src/hooks/useWorkspaces.ts` : `useWorkspaceJobs(name, enabled)`.
- `frontend/src/pages/workspace/WorkspaceJobsTab.tsx` : liste + expansion réservée aux erreurs.

---

## Task 1 : Migration 017 — table `index_job_files`

**Files:**
- Create: `backend/migrations/017_index_job_files.sql`
- Test: `backend/tests/integration/test_migration_017_index_job_files.py` (create)

- [ ] **Step 1 : Écrire la migration**

Create `backend/migrations/017_index_job_files.sql`:
```sql
-- Migration 017 — fichiers traités par job (détail "ce qui a été fait")
CREATE TABLE index_job_files (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id      UUID NOT NULL REFERENCES index_jobs(id) ON DELETE CASCADE,
    path        TEXT NOT NULL,
    change_type TEXT NOT NULL CHECK (change_type IN ('added', 'modified', 'deleted'))
);

CREATE INDEX idx_job_files_job ON index_job_files(job_id);
```

- [ ] **Step 2 : Écrire le test d'intégration (skip local sans PG)**

Create `backend/tests/integration/test_migration_017_index_job_files.py`:
```python
from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_index_job_files_columns(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]: r["data_type"]
            for r in await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'index_job_files'"
            )
        }
    assert {"id", "job_id", "path", "change_type"}.issubset(cols.keys())
    assert cols["job_id"] == "uuid"


@pytest.mark.asyncio
async def test_index_job_files_check_change_type(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        job_id = await _seed_job(conn)
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO index_job_files (job_id, path, change_type) "
                "VALUES ($1, 'x.md', 'renamed')",
                job_id,
            )


@pytest.mark.asyncio
async def test_index_job_files_cascade_on_job_delete(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        job_id = await _seed_job(conn)
        await conn.execute(
            "INSERT INTO index_job_files (job_id, path, change_type) "
            "VALUES ($1, 'a.md', 'added')",
            job_id,
        )
        await conn.execute("DELETE FROM index_jobs WHERE id=$1", job_id)
        n = await conn.fetchval(
            "SELECT count(*) FROM index_job_files WHERE job_id=$1", job_id
        )
    assert n == 0


async def _seed_job(conn: asyncpg.Connection) -> str:
    from hashlib import sha256

    dek = "x" * 32
    api_key = "mig017"
    fp = sha256(api_key.encode()).hexdigest()
    ws_id = await conn.fetchval(
        "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
        "VALUES ($1, pgp_sym_encrypt($2::text, $3::text)::bytea, $4, 'c', 'b') RETURNING id",
        "ws_mig017", api_key, dek, fp,
    )
    return await conn.fetchval(
        "INSERT INTO index_jobs (workspace_id, triggered_by, status) "
        "VALUES ($1, 'manual', 'done') RETURNING id",
        ws_id,
    )
```

- [ ] **Step 3 : Vérifier la collecte (run réel nécessite PG)**

Run: `cd backend && uv run pytest tests/integration/test_migration_017_index_job_files.py --collect-only -q`
Expected: 3 tests collectés sans erreur. (Exécution réelle = skip local sans PG.)

- [ ] **Step 4 : Commit**

```bash
git add backend/migrations/017_index_job_files.sql backend/tests/integration/test_migration_017_index_job_files.py
git commit -m "feat(db): migration 017 table index_job_files"
```

---

## Task 2 : Executor — collecte et persistance des fichiers traités

**Files:**
- Modify: `backend/src/rag/sync/executor.py` (phase « 4. Traite les fichiers » et « 6. Mark done »)
- Test: `backend/tests/integration/test_sync_executor.py` (ajout d'un test)

- [ ] **Step 1 : Écrire le test d'intégration (skip local sans PG)**

Dans `backend/tests/integration/test_sync_executor.py`, ajouter ce test à la fin du fichier (il réutilise les helpers déjà présents `_make_workspace_with_indexer`, `_make_source`, `_make_pending_job`, `NoOpIndexer`, `RepoStorage`, `execute_next_pending_job`, `_StubResolver`, `_StubClientProvider`, `make_bare_repo_with_commits`, `add_commit`) :
```python
@pytest.mark.asyncio
async def test_executor_persists_changed_files(
    session_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    bare = make_bare_repo_with_commits(tmp_path, {"a.md": "v1", "b.md": "v1"})

    ws_id = await _make_workspace_with_indexer(session_pool, "ws_exec_files")
    src_id = await _make_source(session_pool, ws_id, url=f"file://{bare}")
    await _make_pending_job(session_pool, ws_id, src_id)

    storage = RepoStorage(root=tmp_path / "repos")
    indexer = NoOpIndexer(session_pool)
    await execute_next_pending_job(
        config_pool=session_pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
    )

    # 2e sync : modifie b.md, ajoute c.md, supprime a.md
    work = tmp_path / "work"
    add_commit(work, files={"b.md": "v2", "c.md": "v1"}, deletes=["a.md"])
    job2_id = await _make_pending_job(session_pool, ws_id, src_id)
    await execute_next_pending_job(
        config_pool=session_pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
    )

    rows = await session_pool.fetch(
        "SELECT path, change_type FROM index_job_files WHERE job_id=$1 ORDER BY change_type, path",
        job2_id,
    )
    got = {(r["path"], r["change_type"]) for r in rows}
    assert got == {("c.md", "added"), ("b.md", "modified"), ("a.md", "deleted")}


@pytest.mark.asyncio
async def test_executor_skipped_files_not_persisted(
    session_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    bare = make_bare_repo_with_commits(tmp_path, {"a.md": "v1"})

    ws_id = await _make_workspace_with_indexer(session_pool, "ws_exec_skip")
    src_id = await _make_source(session_pool, ws_id, url=f"file://{bare}")
    await _make_pending_job(session_pool, ws_id, src_id)

    storage = RepoStorage(root=tmp_path / "repos")
    indexer = NoOpIndexer(session_pool)
    await execute_next_pending_job(
        config_pool=session_pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
    )

    # 2e sync sans changement → a.md skippé, aucun fichier persisté
    job2_id = await _make_pending_job(session_pool, ws_id, src_id)
    await execute_next_pending_job(
        config_pool=session_pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
    )

    n = await session_pool.fetchval(
        "SELECT count(*) FROM index_job_files WHERE job_id=$1", job2_id
    )
    assert n == 0
```

- [ ] **Step 2 : Vérifier la collecte**

Run: `cd backend && uv run pytest tests/integration/test_sync_executor.py --collect-only -q`
Expected: tests collectés sans erreur (les 2 nouveaux inclus).

- [ ] **Step 3 : Collecter les chemins traités dans l'executor**

Dans `backend/src/rag/sync/executor.py`, phase « 4. Traite les fichiers ». Remplacer le bloc d'initialisation des compteurs (l. 308-310) par :
```python
    # 4. Traite les fichiers
    files_changed = 0
    files_skipped = 0
    changed_files: list[tuple[str, str]] = []  # (path, change_type)
    added_set = set(changes.added)
```
Dans la boucle `for path in changes.added + changes.modified:`, juste après `files_changed += 1` (l. 338), ajouter :
```python
        changed_files.append((path, "added" if path in added_set else "modified"))
```
Dans la boucle `for path in changes.deleted:`, juste après `files_changed += 1` (l. 342), ajouter :
```python
        changed_files.append((path, "deleted"))
```

- [ ] **Step 4 : Persister les fichiers au passage `done`**

Dans la phase « 6. Mark done » (l. 362-376), à l'intérieur du `async with config_pool.acquire() as conn:`, après l'`UPDATE index_jobs ... status='done' ...`, ajouter l'insertion batch :
```python
        if changed_files:
            try:
                await conn.execute(
                    """
                    INSERT INTO index_job_files (job_id, path, change_type)
                    SELECT $1, p, t FROM unnest($2::text[], $3::text[]) AS u(p, t)
                    """,
                    job.job_id,
                    [p for p, _ in changed_files],
                    [t for _, t in changed_files],
                )
            except Exception:
                log.warning("sync.executor.job_files_persist_failed", job_id=jid)
```
(Le détail des fichiers n'est pas critique : un échec d'insertion ne doit pas faire échouer le job déjà marqué `done`.)

- [ ] **Step 5 : Vérifier la collecte + non-régression unit**

Run: `cd backend && uv run pytest tests/integration/test_sync_executor.py --collect-only -q && uv run pytest tests/unit -q`
Expected: collecte OK ; unit : seul `test_source_create_git_minimal` (pré-existant, hors scope) échoue, aucune nouvelle régression.

- [ ] **Step 6 : Lint + commit**

```bash
cd backend && uv run ruff check src/rag/sync/executor.py
git add backend/src/rag/sync/executor.py backend/tests/integration/test_sync_executor.py
git commit -m "feat(sync): persiste les fichiers traités par job dans index_job_files"
```

---

## Task 3 : Erreur `JobNotFound` + DTOs réponse

**Files:**
- Modify: `backend/src/rag/api/errors.py`
- Modify: `backend/src/rag/schemas/admin.py`
- Test: `backend/tests/unit/schemas/test_job_files_dto.py` (create)

- [ ] **Step 1 : Écrire le test unit**

Create `backend/tests/unit/schemas/test_job_files_dto.py`:
```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.schemas.admin import JobFileEntry, JobFilesResponse


def test_job_file_entry_valid() -> None:
    e = JobFileEntry.model_validate({"path": "docs/a.md", "change_type": "added"})
    assert e.path == "docs/a.md"
    assert e.change_type == "added"


def test_job_file_entry_rejects_bad_change_type() -> None:
    with pytest.raises(ValidationError):
        JobFileEntry.model_validate({"path": "a.md", "change_type": "renamed"})


def test_job_files_response_shape() -> None:
    resp = JobFilesResponse.model_validate(
        {
            "files": [{"path": "a.md", "change_type": "deleted"}],
            "total": 1,
            "limit": 1000,
        }
    )
    assert resp.total == 1
    assert resp.limit == 1000
    assert resp.files[0].change_type == "deleted"
```

- [ ] **Step 2 : Run, confirm failure**

Run: `cd backend && uv run pytest tests/unit/schemas/test_job_files_dto.py -v`
Expected: FAIL — `ImportError: cannot import name 'JobFileEntry'`.

- [ ] **Step 3 : Ajouter les DTOs**

Dans `backend/src/rag/schemas/admin.py`, après la classe `JobResponse` (la classe qui contient `files_changed`/`files_skipped`, vers l. 160), ajouter (`Literal` et `BaseModel` sont déjà importés en tête) :
```python
class JobFileEntry(BaseModel):
    path: str
    change_type: Literal["added", "modified", "deleted"]


class JobFilesResponse(BaseModel):
    files: list[JobFileEntry]
    total: int
    limit: int
```

- [ ] **Step 4 : Ajouter l'erreur `JobNotFound`**

Dans `backend/src/rag/api/errors.py`, après la classe `SourceNotFound`, ajouter :
```python
class JobNotFound(AdminError):
    http_status = 404

    def __init__(self, job_id: str) -> None:
        super().__init__(job_id)
        self.job_id = job_id

    def to_payload(self) -> dict[str, object]:
        return {"error": "job_not_found", "id": self.job_id}
```

- [ ] **Step 5 : Run, confirm pass**

Run: `cd backend && uv run pytest tests/unit/schemas/test_job_files_dto.py -v`
Expected: PASS — 3 passed.

- [ ] **Step 6 : Commit**

```bash
git add backend/src/rag/schemas/admin.py backend/src/rag/api/errors.py backend/tests/unit/schemas/test_job_files_dto.py
git commit -m "feat(api): DTOs JobFileEntry/JobFilesResponse + erreur JobNotFound"
```

---

## Task 4 : Service `list_job_files` + endpoint API

**Files:**
- Modify: `backend/src/rag/services/jobs.py`
- Modify: `backend/src/rag/api/admin.py`
- Test: `backend/tests/integration/test_services_jobs.py` (ajout)

- [ ] **Step 1 : Écrire le test d'intégration (skip local sans PG)**

Dans `backend/tests/integration/test_services_jobs.py`, ajouter (vérifier/compléter les imports en tête : `from rag.services.jobs import list_job_files` et `from rag.api.errors import JobNotFound`) ces tests à la fin :
```python
@pytest.mark.asyncio
async def test_list_job_files_returns_files(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ('ws_jf', pgp_sym_encrypt('k'::text, 'x'::text)::bytea, 'fp', 'c', 'b') "
            "RETURNING id"
        )
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status) "
            "VALUES ($1, 'manual', 'done') RETURNING id",
            ws_id,
        )
        await conn.execute(
            "INSERT INTO index_job_files (job_id, path, change_type) "
            "VALUES ($1, 'b.md', 'modified'), ($1, 'a.md', 'added')",
            job_id,
        )

    result = await list_job_files(
        config_pool=session_pool, workspace_name="ws_jf", job_id=str(job_id)
    )
    assert result["total"] == 2
    assert result["limit"] == 1000
    assert {(f["path"], f["change_type"]) for f in result["files"]} == {
        ("a.md", "added"),
        ("b.md", "modified"),
    }


@pytest.mark.asyncio
async def test_list_job_files_unknown_job_raises(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ('ws_jf2', pgp_sym_encrypt('k'::text, 'x'::text)::bytea, 'fp2', 'c', 'b')"
        )
    from uuid import uuid4

    with pytest.raises(JobNotFound):
        await list_job_files(
            config_pool=session_pool, workspace_name="ws_jf2", job_id=str(uuid4())
        )
```
(Si `test_services_jobs.py` n'a pas `MIGRATIONS_DIR` / `cleanup_ws_dbs` / `run_migrations` importés, s'aligner sur le haut du fichier existant — il teste déjà des jobs, donc ces helpers y sont présents ou importables comme dans les autres tests d'intégration.)

- [ ] **Step 2 : Vérifier la collecte**

Run: `cd backend && uv run pytest tests/integration/test_services_jobs.py -k "job_files" --collect-only -q`
Expected: 2 tests collectés sans erreur.

- [ ] **Step 3 : Implémenter le service**

Dans `backend/src/rag/services/jobs.py` :
- Ajouter l'import en tête : `from rag.api.errors import JobNotFound` (si `WorkspaceNotFound` est déjà importé depuis `rag.api.errors`, ajouter `JobNotFound` à la même ligne).
- Ajouter la fonction après `list_jobs` :
```python
async def list_job_files(
    config_pool: asyncpg.Pool, *, workspace_name: str, job_id: str, limit: int = 1000
) -> dict[str, Any]:
    """Fichiers traités par un job (added/modified/deleted), limités à `limit`.

    Lève JobNotFound si le job n'appartient pas au workspace.
    """
    owner = await fetch_one(
        config_pool,
        """
        SELECT j.id FROM index_jobs j
        JOIN workspaces w ON w.id = j.workspace_id
        WHERE j.id = $1::uuid AND w.name = $2
        """,
        job_id,
        workspace_name,
    )
    if owner is None:
        raise JobNotFound(job_id)

    files = await fetch_all(
        config_pool,
        """
        SELECT path, change_type FROM index_job_files
        WHERE job_id = $1::uuid
        ORDER BY change_type, path
        LIMIT $2
        """,
        job_id,
        limit,
    )
    total = await fetch_one(
        config_pool,
        "SELECT count(*) AS n FROM index_job_files WHERE job_id = $1::uuid",
        job_id,
    )
    return {
        "files": [{"path": r["path"], "change_type": r["change_type"]} for r in files],
        "total": int(total["n"]),
        "limit": limit,
    }
```

- [ ] **Step 4 : Ajouter l'endpoint**

Dans `backend/src/rag/api/admin.py` :
- Ajouter `JobFilesResponse` à l'import des schémas admin (là où `JobResponse` est importé).
- Ajouter, dans la section Jobs (près de l'endpoint sync), l'endpoint :
```python
    @router.get("/workspaces/{name}/jobs/{job_id}/files")
    async def get_job_files(name: str, job_id: str, request: Request) -> JobFilesResponse:
        from rag.services.jobs import list_job_files

        result = await list_job_files(
            config_pool=_config_pool(request),
            workspace_name=name,
            job_id=job_id,
        )
        return JobFilesResponse(**result)
```

- [ ] **Step 5 : Vérifier collecte + import + lint**

Run:
```
cd backend && uv run pytest tests/integration/test_services_jobs.py -k "job_files" --collect-only -q
cd backend && uv run python -c "import rag.api.admin"
cd backend && uv run ruff check src/rag/services/jobs.py src/rag/api/admin.py
```
Expected: collecte OK ; import OK ; ruff `All checks passed!`.

- [ ] **Step 6 : Commit**

```bash
git add backend/src/rag/services/jobs.py backend/src/rag/api/admin.py backend/tests/integration/test_services_jobs.py
git commit -m "feat(api): endpoint GET jobs/{id}/files + service list_job_files"
```

---

## Task 5 : Frontend — types, client API, hook

**Files:**
- Modify: `frontend/src/lib/workspaces.types.ts`
- Modify: `frontend/src/lib/workspaces.ts`
- Modify: `frontend/src/hooks/useWorkspaces.ts`

- [ ] **Step 1 : Types**

Dans `frontend/src/lib/workspaces.types.ts`, ajouter après le type `Job` :
```typescript
export type JobFileEntry = {
  path: string;
  change_type: "added" | "modified" | "deleted";
};

export type JobFilesResponse = {
  files: JobFileEntry[];
  total: number;
  limit: number;
};
```

- [ ] **Step 2 : Client API**

Dans `frontend/src/lib/workspaces.ts`, ajouter dans l'objet `workspacesApi`, juste après `listJobs` :
```typescript
  listJobFiles: (name: string, jobId: string) =>
    api.get<JobFilesResponse>(`${BASE}/${name}/jobs/${jobId}/files`),
```
Ajouter `JobFilesResponse` à l'import des types en tête du fichier.

- [ ] **Step 3 : Hook**

Dans `frontend/src/hooks/useWorkspaces.ts`, ajouter après `useWorkspaceJobs` :
```typescript
export function useWorkspaceJobFiles(name: string, jobId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["workspace", name, "jobs", jobId, "files"],
    queryFn: () => workspacesApi.listJobFiles(name, jobId),
    enabled,
  });
}
```
Ajouter `JobFilesResponse` au bloc d'import de types si le type de retour doit être référencé (sinon l'inférence suffit — ne pas importer inutilement).

- [ ] **Step 4 : Vérifier TS strict**

Run: `cd frontend && npx tsc --noEmit`
Expected: aucune erreur.

- [ ] **Step 5 : Commit**

```bash
git add frontend/src/lib/workspaces.types.ts frontend/src/lib/workspaces.ts frontend/src/hooks/useWorkspaces.ts
git commit -m "feat(front): types + client + hook useWorkspaceJobFiles"
```

---

## Task 6 : i18n fr/en — clés du détail

**Files:**
- Modify: `frontend/src/i18n/fr/workspace.json`
- Modify: `frontend/src/i18n/en/workspace.json`

- [ ] **Step 1 : Clés fr**

Dans `frontend/src/i18n/fr/workspace.json`, dans l'objet `jobs` (qui contient déjà `title`, `empty`, `changes`), ajouter une sous-clé `detail` :
```json
    "detail": {
      "source": "Source",
      "started": "Début",
      "finished": "Fin",
      "files": "Fichiers modifiés ({{count}})",
      "added": "ajouté",
      "modified": "modifié",
      "deleted": "supprimé",
      "more": "+ {{count}} fichiers supplémentaires",
      "no_files": "Aucun détail de fichier (job antérieur à cette fonctionnalité).",
      "loading": "Chargement…",
      "error": "Échec du chargement des fichiers."
    }
```
(Insérer en respectant les virgules JSON : après la dernière clé existante de `jobs`, ajouter une virgule puis `"detail": { ... }`.)

- [ ] **Step 2 : Clés en**

Dans `frontend/src/i18n/en/workspace.json`, dans l'objet `jobs`, ajouter :
```json
    "detail": {
      "source": "Source",
      "started": "Started",
      "finished": "Finished",
      "files": "Changed files ({{count}})",
      "added": "added",
      "modified": "modified",
      "deleted": "deleted",
      "more": "+ {{count}} more files",
      "no_files": "No file detail (job predates this feature).",
      "loading": "Loading…",
      "error": "Failed to load files."
    }
```

- [ ] **Step 3 : Valider le JSON**

Run:
```
cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/i18n/fr/workspace.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/en/workspace.json','utf8')); console.log('ok')"
```
Expected: `ok`.

- [ ] **Step 4 : Commit**

```bash
git add frontend/src/i18n/fr/workspace.json frontend/src/i18n/en/workspace.json
git commit -m "feat(i18n): clés jobs.detail pour le panneau de fichiers"
```

---

## Task 7 : Frontend — `JobDetailPanel` + jobs cliquables

**Files:**
- Create: `frontend/src/pages/workspace/JobDetailPanel.tsx`
- Modify: `frontend/src/pages/workspace/WorkspaceJobsTab.tsx`
- Test: `frontend/src/pages/workspace/__tests__/JobDetailPanel.test.tsx` (create)
- Test: `frontend/src/pages/workspace/__tests__/WorkspaceJobsTab.test.tsx` (modify — préserver l'existant)

- [ ] **Step 1 : Écrire le test du panneau (échouera)**

Create `frontend/src/pages/workspace/__tests__/JobDetailPanel.test.tsx`:
```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { JobDetailPanel } from "@/pages/workspace/JobDetailPanel";
import type { Job } from "@/lib/workspaces.types";

const { mockFiles } = vi.hoisted(() => ({
  mockFiles: {
    value: {
      data: undefined as
        | { files: { path: string; change_type: string }[]; total: number; limit: number }
        | undefined,
      isLoading: false,
      isError: false,
    },
  },
}));

vi.mock("@/hooks/useWorkspaces", () => ({
  useWorkspaceJobFiles: () => mockFiles.value,
}));

const baseJob: Job = {
  id: "j1",
  triggered_by: "schedule",
  status: "done",
  files_changed: 3,
  files_skipped: 10,
  error_message: null,
  started_at: "2026-05-28T16:33:01Z",
  finished_at: "2026-05-28T16:33:11Z",
  duration_ms: 10100,
};

describe("JobDetailPanel", () => {
  beforeEach(() => {
    mockFiles.value = { data: undefined, isLoading: false, isError: false };
  });

  it("liste les fichiers modifiés", () => {
    mockFiles.value = {
      data: {
        files: [
          { path: "guides/new.md", change_type: "added" },
          { path: "docs/intro.md", change_type: "modified" },
        ],
        total: 2,
        limit: 1000,
      },
      isLoading: false,
      isError: false,
    };
    renderWithProviders(<JobDetailPanel name="wrk1" job={baseJob} />);
    expect(screen.getByText("guides/new.md")).toBeInTheDocument();
    expect(screen.getByText("docs/intro.md")).toBeInTheDocument();
  });

  it("affiche 'aucun détail' quand la liste est vide", () => {
    mockFiles.value = {
      data: { files: [], total: 0, limit: 1000 },
      isLoading: false,
      isError: false,
    };
    renderWithProviders(<JobDetailPanel name="wrk1" job={baseJob} />);
    expect(screen.getByText(/aucun détail de fichier/i)).toBeInTheDocument();
  });

  it("affiche le message d'erreur du job en erreur", () => {
    mockFiles.value = { data: { files: [], total: 0, limit: 1000 }, isLoading: false, isError: false };
    const errored: Job = { ...baseJob, status: "error", error_message: "boom" };
    renderWithProviders(<JobDetailPanel name="wrk1" job={errored} />);
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("affiche le compteur de fichiers supplémentaires si total > limit", () => {
    mockFiles.value = {
      data: { files: [{ path: "a.md", change_type: "added" }], total: 1500, limit: 1000 },
      isLoading: false,
      isError: false,
    };
    renderWithProviders(<JobDetailPanel name="wrk1" job={baseJob} />);
    expect(screen.getByText(/500/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2 : Run, confirm failure**

Run: `cd frontend && npx vitest run src/pages/workspace/__tests__/JobDetailPanel.test.tsx`
Expected: FAIL — module `JobDetailPanel` introuvable.

- [ ] **Step 3 : Créer `JobDetailPanel.tsx`**

Create `frontend/src/pages/workspace/JobDetailPanel.tsx`:
```typescript
import { useTranslation } from "react-i18next";
import { useWorkspaceJobFiles } from "@/hooks/useWorkspaces";
import type { Job, JobFileEntry } from "@/lib/workspaces.types";

interface Props {
  name: string;
  job: Job;
}

const SIGN: Record<JobFileEntry["change_type"], string> = {
  added: "+",
  modified: "~",
  deleted: "−",
};

const COLOR: Record<JobFileEntry["change_type"], string> = {
  added: "text-green-700",
  modified: "text-amber-700",
  deleted: "text-red-700",
};

function fmt(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export function JobDetailPanel({ name, job }: Props) {
  const { t } = useTranslation("workspace");
  const { data, isLoading, isError } = useWorkspaceJobFiles(name, job.id, true);
  const files = data?.files ?? [];
  const hasError = job.status === "error" && job.error_message;

  return (
    <div className="border-t border-slate-100 px-3 py-2 bg-slate-50 text-xs">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-slate-600 mb-2">
        <span>{t("jobs.detail.started")} : {fmt(job.started_at)}</span>
        <span>{t("jobs.detail.finished")} : {fmt(job.finished_at)}</span>
      </div>

      {hasError && (
        <div className="mb-2 rounded bg-red-50 px-2 py-1 text-red-700 font-mono">
          {job.error_message}
        </div>
      )}

      {isLoading && <p className="text-slate-500">{t("jobs.detail.loading")}</p>}
      {isError && <p className="text-red-600">{t("jobs.detail.error")}</p>}

      {!isLoading && !isError && files.length === 0 && !hasError && (
        <p className="text-slate-500">{t("jobs.detail.no_files")}</p>
      )}

      {files.length > 0 && (
        <>
          <p className="font-medium text-slate-700 mb-1">
            {t("jobs.detail.files", { count: data?.total ?? files.length })}
          </p>
          <ul className="space-y-0.5 font-mono">
            {files.map((f) => (
              <li key={`${f.change_type}:${f.path}`} className={COLOR[f.change_type]}>
                <span className="inline-block w-3">{SIGN[f.change_type]}</span> {f.path}
              </li>
            ))}
          </ul>
          {data && data.total > data.limit && (
            <p className="text-slate-400 mt-1">
              {t("jobs.detail.more", { count: data.total - data.limit })}
            </p>
          )}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4 : Run, confirm pass**

Run: `cd frontend && npx vitest run src/pages/workspace/__tests__/JobDetailPanel.test.tsx`
Expected: PASS — 4 passed.

- [ ] **Step 5 : Rendre tous les jobs cliquables dans `WorkspaceJobsTab`**

Dans `frontend/src/pages/workspace/WorkspaceJobsTab.tsx` :
- Importer le panneau en tête : `import { JobDetailPanel } from "./JobDetailPanel";`
- Supprimer la restriction `hasError` sur le bouton. Remplacer le bloc `<button ...>` (`onClick`, `disabled`, et le rendu conditionnel du chevron) par une version qui s'applique à tous les jobs :
  - `onClick={() => toggle(job.id)}`
  - retirer l'attribut `disabled`
  - chevron toujours affiché : `{isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}` (supprimer le `<span className="w-3.5" />` et la condition `hasError ?`)
- Remplacer le bloc de rendu conditionnel actuel :
  ```typescript
  {isOpen && hasError && (
    <div className="border-t ...">{job.error_message}</div>
  )}
  ```
  par :
  ```typescript
  {isOpen && <JobDetailPanel name={name} job={job} />}
  ```
- La variable `hasError` n'est alors plus utilisée dans cette fonction → la supprimer (l. 60) pour éviter un warning ESLint `no-unused-vars`.

- [ ] **Step 6 : Mettre à jour le test `WorkspaceJobsTab` (mocks stables !)**

Ouvrir `frontend/src/pages/workspace/__tests__/WorkspaceJobsTab.test.tsx`. Ce test doit maintenant mocker `useWorkspaceJobFiles` (utilisé par `JobDetailPanel`) en plus de `useWorkspaceJobs`. **Tout hook mocké renvoyant un objet doit renvoyer une référence STABLE via `vi.hoisted`** (sinon OOM par boucle de re-render). Adapter le `vi.mock("@/hooks/useWorkspaces", ...)` pour exposer aussi :
```typescript
  useWorkspaceJobFiles: () => ({ data: { files: [], total: 0, limit: 1000 }, isLoading: false, isError: false }),
```
en veillant à ce que l'objet retourné soit une **constante hoistée** (déclarée via `vi.hoisted`, réutilisée à chaque appel), pas un littéral recréé à chaque rendu. Ajouter un test : un job `done` est désormais cliquable (le chevron est présent et le bouton n'est pas `disabled`). Conserver les tests existants.

- [ ] **Step 7 : Run scoped, confirm pass**

Run:
```
cd frontend && npx vitest run src/pages/workspace/__tests__/JobDetailPanel.test.tsx src/pages/workspace/__tests__/WorkspaceJobsTab.test.tsx
```
Expected: tous verts. (Lancer fichier par fichier, jamais la suite complète.)

- [ ] **Step 8 : TS strict + lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: pas d'erreur sur les fichiers modifiés.

- [ ] **Step 9 : Commit**

```bash
git add frontend/src/pages/workspace/JobDetailPanel.tsx frontend/src/pages/workspace/WorkspaceJobsTab.tsx frontend/src/pages/workspace/__tests__/JobDetailPanel.test.tsx frontend/src/pages/workspace/__tests__/WorkspaceJobsTab.test.tsx
git commit -m "feat(front): jobs cliquables + panneau détail des fichiers traités"
```

---

## Vérification finale

- [ ] **Backend unit** : `cd backend && uv run pytest tests/unit -q` → seul `test_source_create_git_minimal` (pré-existant) échoue.
- [ ] **Backend intégration** (PG requis, sur l'infra) : migrations 017, executor, services jobs.
- [ ] **Frontend ciblé** : `npx vitest run` sur `JobDetailPanel` et `WorkspaceJobsTab` → verts ; `npx tsc --noEmit` clean.

## Notes / hors scope

- Backfill rétroactif des jobs existants : impossible (chemins non conservés).
- « Charger plus » au-delà de 1000 fichiers : YAGNI.
- Persistance des fichiers ignorés (skipped) : exclue par design.
