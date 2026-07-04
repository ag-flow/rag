# M18 — Surface MCP déterministe (index_status, search_files, get_document)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter 3 outils MCP déterministes qui complètent `rag_search` : `index_status` (fraîcheur), `search_files` (littéral/regex), `get_document` (lecture intégrale + flag confidentialité).

**Architecture :** Deux migrations minimes (049 config `allow_full_read`, ws 004 `sections.section_index`) ; une couche DB `mcp_tools.py` avec les requêtes ; 3 `@_mcp.tool()` dans `mcp_standard.py` qui lisent `_ws_ctx` (déjà étendu en M17). `get_document` reconstruit depuis `sections ORDER BY section_index` avec fallback legacy `embeddings ORDER BY chunk_index`. `_WsCtx` a déjà `workspace_id` et `config_pool` depuis M17 — pas de doublon.

**Tech Stack:** Python 3.12, asyncpg, FastMCP, pytest-asyncio

## Global Constraints

- `from __future__ import annotations` en tête de chaque fichier Python
- Tests TDD : rouge → vert → commit
- Toutes les requêtes SQL paramétrées (jamais de f-string SQL)
- `allow_full_read=True` par défaut → **additif, zéro régression**
- `section_index` backfillé par `id` croissant (meilleure approximation des sections existantes)
- Branche `dev` uniquement

---

## Fichiers impactés

| Fichier | Action |
|---|---|
| `backend/migrations/049_allow_full_read.sql` | **Nouveau** |
| `backend/src/rag/db/workspace_migrations/versions/004_section_index.sql` | **Nouveau** |
| `backend/src/rag/db/workspace_structured.py` | `ParentRow.section_index`, `_upsert_sections` |
| `backend/src/rag/indexer/real.py` | Passer `section_index=idx` dans `parent_rows` |
| `backend/src/rag/db/mcp_tools.py` | **Nouveau** — fonctions DB pour les 3 outils |
| `backend/src/rag/api/mcp_standard.py` | 3 nouveaux `@_mcp.tool()` |
| `backend/tests/unit/db/test_mcp_tools.py` | **Nouveau** |
| `backend/tests/unit/api/test_mcp_tools_integration.py` | **Nouveau** |
| `backend/tests/unit/db/test_workspace_structured.py` | Adapter si existant |

---

### Task 1 — Migrations + `section_index` dans le pipeline structuré

**Files:**
- Create: `backend/migrations/049_allow_full_read.sql`
- Create: `backend/src/rag/db/workspace_migrations/versions/004_section_index.sql`
- Modify: `backend/src/rag/db/workspace_structured.py`
- Modify: `backend/src/rag/indexer/real.py`

**Interfaces:**
- Produit: `ParentRow(section_key, content, metadata, section_index: int = 0)`
- Produit: `upsert_structured` écrit `section_index` dans `sections`

- [ ] **Step 1 : Créer les migrations**

`backend/migrations/049_allow_full_read.sql` :
```sql
-- Migration 049 — flag confidentialité par workspace pour get_document
--
-- allow_full_read=TRUE (défaut) → comportement inchangé pour tous les workspaces existants.
-- Mettre à FALSE pour un workspace sensible : get_document refusé, search_files autorisé.

ALTER TABLE workspaces
    ADD COLUMN allow_full_read BOOLEAN NOT NULL DEFAULT TRUE;
```

`backend/src/rag/db/workspace_migrations/versions/004_section_index.sql` :
```sql
-- Workspace migration 004 — ordre déclaré des sections parentes
--
-- section_index : position de la section dans le document (0-based), déclarée au chunking.
-- Nécessaire pour get_document (M18) et chunk-viz (M15) : ORDER BY section_index garantit
-- l'ordre du doc original indépendamment de l'id (ON CONFLICT DO UPDATE ne change pas l'id).
--
-- Backfill : ORDER BY id ≈ ordre d'insertion = meilleure approximation pour les sections
-- existantes. Les nouvelles indexations renseignent section_index natif.

ALTER TABLE sections
    ADD COLUMN section_index INT;

WITH ranked AS (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY path ORDER BY id) - 1 AS idx
    FROM sections
)
UPDATE sections
SET section_index = ranked.idx
FROM ranked
WHERE sections.id = ranked.id;
```

- [ ] **Step 2 : Modifier `workspace_structured.py`**

Lire le fichier. Deux modifications :

**2a** — Ajouter `section_index: int = 0` à `ParentRow` :
```python
@dataclass(frozen=True)
class ParentRow:
    section_key: str
    content: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    section_index: int = 0
```

**2b** — Modifier `_upsert_sections` pour écrire et mettre à jour `section_index`.

Trouver la requête INSERT INTO sections. La remplacer par :
```python
section_id = await conn.fetchval(
    "INSERT INTO sections (path, section_key, content, metadata, section_index) "
    "VALUES ($1,$2,$3,$4::jsonb,$5) "
    "ON CONFLICT (path, section_key) DO UPDATE SET "
    "content=EXCLUDED.content, metadata=EXCLUDED.metadata, "
    "section_index=EXCLUDED.section_index, indexed_at=now() "
    "RETURNING id",
    path,
    parent.section_key,
    parent.content,
    json.dumps(dict(parent.metadata)),
    parent.section_index,
)
```

Note : la signature de `_upsert_sections` reste `(conn, path, parents)` — `parent` itère sur `parents`. Lire la boucle existante pour faire la modification minimale.

- [ ] **Step 3 : Modifier `real.py`**

Lire `_index_structured`. Trouver la construction de `parent_rows`. Ajouter `section_index=idx` :

```python
parent_rows = [
    ParentRow(
        section_key=p.section_key,
        content=p.content,
        metadata={**extra_metadata, **dict(p.metadata)} if extra_metadata else p.metadata,
        section_index=idx,
    )
    for idx, p in enumerate(doc.parents)
]
```

- [ ] **Step 4 : Vérifier non-régression**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/indexer/ tests/unit/db/ -q 2>&1 | tail -5
```

- [ ] **Step 5 : Lint**

```bash
cd /workspaces/admin-rag/backend && uv run ruff check src/rag/db/workspace_structured.py src/rag/indexer/real.py && echo "lint OK"
```

- [ ] **Step 6 : Commit**

```bash
git add backend/migrations/049_allow_full_read.sql \
        backend/src/rag/db/workspace_migrations/versions/004_section_index.sql \
        backend/src/rag/db/workspace_structured.py \
        backend/src/rag/indexer/real.py
git commit -m "feat(db): section_index + allow_full_read — migrations 049 + ws 004"
```

---

### Task 2 — `index_status` (DB + outil MCP + tests)

**Files:**
- Create: `backend/src/rag/db/mcp_tools.py`
- Modify: `backend/src/rag/api/mcp_standard.py`
- Create: `backend/tests/unit/db/test_mcp_tools.py`

**Interfaces:**
- Produit: `get_index_status(config_pool, workspace_id) -> dict`
- Produit: `get_document_status(config_pool, workspace_id, path) -> dict | None`
- Produit: `@_mcp.tool() async def index_status(path=None) -> str`

- [ ] **Step 1 : Créer les tests DB**

Créer `backend/tests/unit/db/test_mcp_tools.py` (section index_status) :

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


class TestGetIndexStatus:
    @pytest.mark.asyncio
    async def test_returns_workspace_aggregate(self):
        from rag.db.mcp_tools import get_index_status

        ws_id = uuid4()
        pool = MagicMock()
        pool.fetchrow = AsyncMock(
            side_effect=[
                # indexed_documents aggregate
                {"documents_count": 42, "last_indexed_at": "2026-01-01T00:00:00Z"},
                # workspace_sources sync
                {"last_indexed_at": "2026-01-01T00:00:00Z", "next_sync_at": None},
                # last index_job
                {"status": "done", "finished_at": "2026-01-01T01:00:00Z"},
            ]
        )
        result = await get_index_status(pool, workspace_id=ws_id)
        assert result["documents_count"] == 42
        assert "sync" in result
        assert result["sync"]["healthy"] is True

    @pytest.mark.asyncio
    async def test_healthy_false_when_last_job_error(self):
        from rag.db.mcp_tools import get_index_status

        ws_id = uuid4()
        pool = MagicMock()
        pool.fetchrow = AsyncMock(
            side_effect=[
                {"documents_count": 10, "last_indexed_at": None},
                {"last_indexed_at": None, "next_sync_at": None},
                {"status": "error", "finished_at": "2026-01-01T01:00:00Z"},
            ]
        )
        result = await get_index_status(pool, workspace_id=ws_id)
        assert result["sync"]["healthy"] is False

    @pytest.mark.asyncio
    async def test_healthy_true_when_no_job_yet(self):
        from rag.db.mcp_tools import get_index_status

        ws_id = uuid4()
        pool = MagicMock()
        pool.fetchrow = AsyncMock(
            side_effect=[
                {"documents_count": 0, "last_indexed_at": None},
                {"last_indexed_at": None, "next_sync_at": None},
                None,  # pas de job
            ]
        )
        result = await get_index_status(pool, workspace_id=ws_id)
        assert result["sync"]["healthy"] is True

    @pytest.mark.asyncio
    async def test_get_document_status_returns_none_when_not_found(self):
        from rag.db.mcp_tools import get_document_status

        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value=None)
        result = await get_document_status(pool, workspace_id=uuid4(), path="a.py")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_document_status_returns_doc_info(self):
        from rag.db.mcp_tools import get_document_status

        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value={
            "path": "a.py",
            "content_hash": "sha256:abc",
            "indexed_at": "2026-01-01",
            "indexer_used": "openai/m",
            "title": None,
        })
        result = await get_document_status(pool, workspace_id=uuid4(), path="a.py")
        assert result is not None
        assert result["path"] == "a.py"
        assert result["content_hash"] == "sha256:abc"
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/db/test_mcp_tools.py -v 2>&1 | head -10
```

- [ ] **Step 3 : Créer `mcp_tools.py`**

Créer `backend/src/rag/db/mcp_tools.py` :

```python
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
import structlog

log = structlog.get_logger(__name__)


async def get_index_status(
    config_pool: asyncpg.Pool,
    *,
    workspace_id: UUID,
) -> dict[str, Any]:
    """Agrégats indexed_documents + bloc sync (workspace_sources + dernier index_job)."""
    agg = await config_pool.fetchrow(
        "SELECT COUNT(*) AS documents_count, MAX(indexed_at) AS last_indexed_at "
        "FROM indexed_documents WHERE workspace_id = $1",
        workspace_id,
    )
    src = await config_pool.fetchrow(
        "SELECT last_indexed_at, next_sync_at FROM workspace_sources WHERE workspace_id = $1 LIMIT 1",
        workspace_id,
    )
    job = await config_pool.fetchrow(
        "SELECT status, finished_at FROM index_jobs "
        "WHERE workspace_id = $1 ORDER BY finished_at DESC NULLS LAST LIMIT 1",
        workspace_id,
    )
    healthy = True if (job is None or job["status"] != "error") else False
    return {
        "documents_count": agg["documents_count"] if agg else 0,
        "last_indexed_at": str(agg["last_indexed_at"]) if agg and agg["last_indexed_at"] else None,
        "sync": {
            "last_indexed_at": str(src["last_indexed_at"]) if src and src["last_indexed_at"] else None,
            "next_sync_at": str(src["next_sync_at"]) if src and src["next_sync_at"] else None,
            "last_job_status": job["status"] if job else None,
            "last_job_finished_at": str(job["finished_at"]) if job and job["finished_at"] else None,
            "healthy": healthy,
        },
    }


async def get_document_status(
    config_pool: asyncpg.Pool,
    *,
    workspace_id: UUID,
    path: str,
) -> dict[str, Any] | None:
    """Fraîcheur et hash d'un document indexé."""
    row = await config_pool.fetchrow(
        "SELECT path, content_hash, indexed_at, indexer_used, title "
        "FROM indexed_documents WHERE workspace_id = $1 AND path = $2",
        workspace_id,
        path,
    )
    if row is None:
        return None
    return {
        "path": row["path"],
        "content_hash": row["content_hash"],
        "indexed_at": str(row["indexed_at"]) if row["indexed_at"] else None,
        "indexer_used": row["indexer_used"],
        "title": row["title"],
    }
```

- [ ] **Step 4 : Lancer les tests DB**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/db/test_mcp_tools.py -v
```
Attendu : 5 tests PASSED.

- [ ] **Step 5 : Ajouter `index_status` dans `mcp_standard.py`**

Lire le fichier. Ajouter l'import au niveau module :
```python
from rag.db.mcp_tools import get_document_status, get_index_status, reconstruct_document, search_files_in_workspace
```
(les fonctions `reconstruct_document` et `search_files_in_workspace` seront ajoutées aux Tasks 3 et 4 — utiliser des imports tardifs si nécessaire pour éviter un NameError avant que les fonctions existent)

Alternative propre : importer chaque fonction localement dans son tool.

Ajouter après `get_enrichment` :

```python
@_mcp.tool()
async def index_status(path: str | None = None) -> str:
    """Fraîcheur et couverture de l'index du workspace courant.

    Sans argument : agrégats globaux (nb docs, dernière indexation, état sync).
    Avec path : hash et fraîcheur du document spécifique.
    """
    import json as _json
    from rag.db.mcp_tools import get_document_status, get_index_status

    ctx = _ws_ctx.get()
    if path:
        data = await get_document_status(ctx.config_pool, workspace_id=ctx.workspace_id, path=path)
        if data is None:
            return f"Document '{path}' non trouvé dans l'index."
        return _json.dumps(data, ensure_ascii=False, indent=2)
    data = await get_index_status(ctx.config_pool, workspace_id=ctx.workspace_id)
    return _json.dumps({"workspace": ctx.workspace_name, **data}, ensure_ascii=False, indent=2)
```

- [ ] **Step 6 : Lint**

```bash
cd /workspaces/admin-rag/backend && uv run ruff check src/rag/db/mcp_tools.py src/rag/api/mcp_standard.py && echo "lint OK"
```

- [ ] **Step 7 : Commit**

```bash
git add backend/src/rag/db/mcp_tools.py backend/src/rag/api/mcp_standard.py backend/tests/unit/db/test_mcp_tools.py
git commit -m "feat(mcp): outil index_status — fraîcheur et couverture de l'index"
```

---

### Task 3 — `search_files` (DB + outil MCP + tests)

**Files:**
- Modify: `backend/src/rag/db/mcp_tools.py`
- Modify: `backend/src/rag/api/mcp_standard.py`
- Modify: `backend/tests/unit/db/test_mcp_tools.py`

**Interfaces:**
- Produit: `search_files_in_workspace(ws_pool, *, pattern, mode, top_k) -> list[dict]`
  - mode: `"exact"` (content_tsv), `"substring"` (ILIKE), `"regex"` (~ opérateur)
- Produit: `@_mcp.tool() async def search_files(pattern, mode="exact", top_k=20) -> str`

- [ ] **Step 1 : Ajouter les tests `search_files` dans `test_mcp_tools.py`**

Ajouter à la fin de `backend/tests/unit/db/test_mcp_tools.py` :

```python
class TestSearchFilesInWorkspace:
    def _make_ws_pool(self, rows: list[dict]) -> MagicMock:
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=rows)
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=conn)
        return pool

    @pytest.mark.asyncio
    async def test_exact_mode_returns_hits(self):
        from rag.db.mcp_tools import search_files_in_workspace

        rows = [{"path": "a.py", "content": "RAG_MASTER_KEY env var", "chunk_index": 0, "metadata": None}]
        pool = self._make_ws_pool(rows)
        hits = await search_files_in_workspace(pool, pattern="RAG_MASTER_KEY", mode="exact", top_k=10)
        assert len(hits) == 1
        assert hits[0]["path"] == "a.py"

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_list(self):
        from rag.db.mcp_tools import search_files_in_workspace

        pool = self._make_ws_pool([])
        hits = await search_files_in_workspace(pool, pattern="notfound", mode="substring", top_k=5)
        assert hits == []

    @pytest.mark.asyncio
    async def test_regex_mode_uses_tilde_operator(self):
        from rag.db.mcp_tools import search_files_in_workspace

        pool = self._make_ws_pool([])
        await search_files_in_workspace(pool, pattern="def .+:", mode="regex", top_k=5)
        conn = pool.acquire.return_value.__aenter__.return_value
        sql = conn.fetch.call_args[0][0]
        assert "~" in sql

    @pytest.mark.asyncio
    async def test_exact_mode_uses_content_tsv(self):
        from rag.db.mcp_tools import search_files_in_workspace

        pool = self._make_ws_pool([])
        await search_files_in_workspace(pool, pattern="mytoken", mode="exact", top_k=5)
        conn = pool.acquire.return_value.__aenter__.return_value
        sql = conn.fetch.call_args[0][0]
        assert "content_tsv" in sql or "websearch_to_tsquery" in sql
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/db/test_mcp_tools.py::TestSearchFilesInWorkspace -v 2>&1 | head -10
```

- [ ] **Step 3 : Implémenter `search_files_in_workspace` dans `mcp_tools.py`**

Ajouter à la fin de `backend/src/rag/db/mcp_tools.py` :

```python
async def search_files_in_workspace(
    ws_pool: asyncpg.Pool,
    *,
    pattern: str,
    mode: str = "exact",
    top_k: int = 20,
) -> list[dict[str, Any]]:
    """Recherche littérale dans le contenu indexé (embeddings).

    Modes :
    - exact      : content_tsv @@ websearch_to_tsquery (token, sans stemming)
    - substring  : ILIKE '%pattern%'
    - regex      : content ~ pattern (seq scan)

    Résultats dédupliqués par path (un path → extrait du meilleur chunk).
    Pas de dédup section : on cherche dans le contenu enfant directement.
    """
    async with ws_pool.acquire() as conn:
        if mode == "exact":
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (path) path, content, chunk_index, metadata
                FROM embeddings
                WHERE content_tsv @@ websearch_to_tsquery('simple', $1)
                ORDER BY path, chunk_index
                LIMIT $2
                """,
                pattern,
                top_k,
            )
        elif mode == "regex":
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (path) path, content, chunk_index, metadata
                FROM embeddings
                WHERE content ~ $1
                ORDER BY path, chunk_index
                LIMIT $2
                """,
                pattern,
                top_k,
            )
        else:  # substring
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (path) path, content, chunk_index, metadata
                FROM embeddings
                WHERE content ILIKE '%' || $1 || '%'
                ORDER BY path, chunk_index
                LIMIT $2
                """,
                pattern,
                top_k,
            )
    return [
        {
            "path": r["path"],
            "chunk_index": r["chunk_index"],
            "content": r["content"],
            "enrichment_key": (
                dict(r["metadata"]).get("enrichment_key") if r["metadata"] else None
            ),
            "source_path": (
                dict(r["metadata"]).get("source_path") if r["metadata"] else None
            ),
        }
        for r in rows
    ]
```

- [ ] **Step 4 : Ajouter `search_files` dans `mcp_standard.py`**

Ajouter après `index_status` :

```python
@_mcp.tool()
async def search_files(
    pattern: str,
    mode: str = "exact",
    top_k: int = 20,
) -> str:
    """Recherche littérale dans le corpus indexé du workspace.

    mode: 'exact' (token, via content_tsv — recommandé pour identifiants),
          'substring' (ILIKE, sous-chaîne),
          'regex' (opérateur ~ Postgres — lent sur gros corpus).
    top_k : max de paths retournés (dédup par path).
    """
    from rag.db.mcp_tools import search_files_in_workspace

    ctx = _ws_ctx.get()
    ws_pool = await ctx.pool_registry.get_workspace_pool(ctx.workspace_name, ctx.rag_cnx)
    hits = await search_files_in_workspace(ws_pool, pattern=pattern, mode=mode, top_k=top_k)

    if not hits:
        return f"Aucune occurrence de '{pattern}' trouvée (mode={mode})."

    parts = []
    for h in hits:
        label = h["path"]
        if h.get("enrichment_key"):
            label = f"{h.get('source_path') or h['path']} [{h['enrichment_key']}]"
        parts.append(f"[{label} — chunk {h['chunk_index']}]\n{h['content']}")

    log.info("mcp_standard.search_files", workspace=ctx.workspace_name, hits=len(hits), mode=mode)
    return f"**{len(hits)} fichier(s)** contenant '{pattern}' :\n\n" + "\n\n---\n\n".join(parts)
```

- [ ] **Step 5 : Lancer les tests**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/db/test_mcp_tools.py -v
```
Attendu : tous verts.

- [ ] **Step 6 : Lint**

```bash
cd /workspaces/admin-rag/backend && uv run ruff check src/rag/db/mcp_tools.py src/rag/api/mcp_standard.py && echo "lint OK"
```

- [ ] **Step 7 : Commit**

```bash
git add backend/src/rag/db/mcp_tools.py backend/src/rag/api/mcp_standard.py backend/tests/unit/db/test_mcp_tools.py
git commit -m "feat(mcp): outil search_files — littéral exact/substring/regex"
```

---

### Task 4 — `get_document` (reconstruction + allow_full_read + tests)

**Files:**
- Modify: `backend/src/rag/db/mcp_tools.py`
- Modify: `backend/src/rag/api/mcp_standard.py`
- Modify: `backend/tests/unit/db/test_mcp_tools.py`

**Interfaces:**
- Produit: `reconstruct_document(ws_pool, config_pool, *, workspace_id, path) -> dict | None`
  - `{"content": str, "is_legacy": bool, "is_code_structured": bool, "sections_count": int}`
- Produit: `@_mcp.tool() async def get_document(path) -> str` — refuse si `allow_full_read=False`

- [ ] **Step 1 : Ajouter les tests `reconstruct_document` dans `test_mcp_tools.py`**

Ajouter à la fin de `test_mcp_tools.py` :

```python
class TestReconstructDocument:
    def _make_ws_pool_sections(self, rows: list[dict]) -> MagicMock:
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=rows)
        conn.fetchval = AsyncMock(return_value=None)
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=conn)
        return pool

    @pytest.mark.asyncio
    async def test_returns_none_when_path_not_found(self):
        from rag.db.mcp_tools import reconstruct_document

        ws_pool = self._make_ws_pool_sections([])
        config_pool = MagicMock()
        result = await reconstruct_document(ws_pool, config_pool, workspace_id=uuid4(), path="a.py")
        assert result is None

    @pytest.mark.asyncio
    async def test_reconstructs_from_sections(self):
        from rag.db.mcp_tools import reconstruct_document

        rows = [
            {"content": "# Section 1\nHello", "section_index": 0, "section_key": "s1", "metadata": None},
            {"content": "# Section 2\nWorld", "section_index": 1, "section_key": "s2", "metadata": None},
        ]
        ws_pool = self._make_ws_pool_sections(rows)
        ws_pool.acquire.return_value.__aenter__.return_value.fetchval = AsyncMock(return_value=None)
        config_pool = MagicMock()
        result = await reconstruct_document(ws_pool, config_pool, workspace_id=uuid4(), path="doc.md")
        assert result is not None
        assert "Section 1" in result["content"]
        assert "Section 2" in result["content"]
        assert result["is_legacy"] is False
        assert result["sections_count"] == 2

    @pytest.mark.asyncio
    async def test_legacy_fallback_when_no_sections(self):
        from rag.db.mcp_tools import reconstruct_document

        conn = MagicMock()
        # First fetch (sections) → []
        # Second fetch (legacy embeddings) → rows
        legacy_rows = [
            {"content": "chunk 0 text", "chunk_index": 0},
            {"content": "chunk 1 text", "chunk_index": 1},
        ]
        conn.fetch = AsyncMock(side_effect=[[], legacy_rows])
        conn.fetchval = AsyncMock(return_value=None)
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        ws_pool = MagicMock()
        ws_pool.acquire = MagicMock(return_value=conn)

        config_pool = MagicMock()
        result = await reconstruct_document(ws_pool, config_pool, workspace_id=uuid4(), path="legacy.py")
        assert result is not None
        assert result["is_legacy"] is True
        assert "chunk 0 text" in result["content"]
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/db/test_mcp_tools.py::TestReconstructDocument -v 2>&1 | head -10
```

- [ ] **Step 3 : Implémenter `reconstruct_document` dans `mcp_tools.py`**

Ajouter à la fin de `mcp_tools.py` :

```python
async def reconstruct_document(
    ws_pool: asyncpg.Pool,
    config_pool: asyncpg.Pool,
    *,
    workspace_id: UUID,
    path: str,
) -> dict[str, Any] | None:
    """Reconstruit le contenu d'un path depuis les sections (ou fallback embeddings legacy).

    Option A (M18 reco) : sections ordonnées par section_index.
    Fallback legacy : embeddings sans section_id, ordonnés par chunk_index.

    Note : la reconstruction code est approximative (tree-sitter découpe par symboles,
    pas ligne à ligne). Le contenu est celui indexé, pas le fichier source original.
    """
    async with ws_pool.acquire() as conn:
        # Tentative 1 : sections structurées
        sections = await conn.fetch(
            """
            SELECT content, section_index, section_key, metadata
            FROM sections
            WHERE path = $1
            ORDER BY section_index NULLS LAST, id
            """,
            path,
        )

        if sections:
            parts = [r["content"] for r in sections]
            # Déterminer si c'est du code structuré (sections avec metadata scope)
            is_code = any(
                r["metadata"] and dict(r["metadata"]).get("scope") for r in sections
            )
            return {
                "content": "\n\n".join(parts),
                "is_legacy": False,
                "is_code_structured": bool(is_code),
                "sections_count": len(sections),
            }

        # Fallback legacy : embeddings sans section_id
        chunks = await conn.fetch(
            """
            SELECT content, chunk_index
            FROM embeddings
            WHERE path = $1 AND section_id IS NULL
            ORDER BY chunk_index
            """,
            path,
        )

    if not chunks:
        return None

    parts = [r["content"] for r in chunks]
    return {
        "content": "\n\n".join(parts),
        "is_legacy": True,
        "is_code_structured": False,
        "sections_count": len(chunks),
    }
```

- [ ] **Step 4 : Ajouter `get_document` dans `mcp_standard.py`**

Ajouter après `search_files` :

```python
@_mcp.tool()
async def get_document(path: str) -> str:
    """Retourne le contenu indexé d'un document.

    Reconstruit depuis les sections parentes (ordonnées). Pour le code, la
    reconstruction est **par symboles** (classes/fonctions), pas ligne à ligne —
    fidèle prose/markdown, approximatif code. Refusé si le workspace est en mode
    lecture restreinte (allow_full_read=False).
    """
    from rag.db.mcp_tools import reconstruct_document

    ctx = _ws_ctx.get()

    # Vérifier le flag allow_full_read
    allow = await ctx.config_pool.fetchval(
        "SELECT allow_full_read FROM workspaces WHERE id = $1",
        ctx.workspace_id,
    )
    if allow is False:
        return (
            f"Lecture complète non autorisée pour ce workspace. "
            f"Utilisez rag_search pour des extraits contextuels."
        )

    ws_pool = await ctx.pool_registry.get_workspace_pool(ctx.workspace_name, ctx.rag_cnx)
    result = await reconstruct_document(
        ws_pool, ctx.config_pool, workspace_id=ctx.workspace_id, path=path
    )

    if result is None:
        return f"Document '{path}' non trouvé dans l'index."

    header = f"**{path}** ({result['sections_count']} section(s))"
    if result["is_code_structured"]:
        header += " — reconstruction par symboles (pas ligne à ligne)"
    if result["is_legacy"]:
        header += " — engine legacy (chunks plats)"

    log.info("mcp_standard.get_document", workspace=ctx.workspace_name, path=path)
    return f"{header}\n\n{result['content']}"
```

- [ ] **Step 5 : Lancer tous les tests DB**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/db/test_mcp_tools.py -v
```
Attendu : tous verts.

- [ ] **Step 6 : Lint**

```bash
cd /workspaces/admin-rag/backend && uv run ruff check src/rag/db/mcp_tools.py src/rag/api/mcp_standard.py && echo "lint OK"
```

- [ ] **Step 7 : Commit**

```bash
git add backend/src/rag/db/mcp_tools.py backend/src/rag/api/mcp_standard.py backend/tests/unit/db/test_mcp_tools.py
git commit -m "feat(mcp): outil get_document — reconstruction sections + flag allow_full_read"
```

---

### Task 5 — Non-régression globale

- [ ] **Step 1 : Lancer tous les tests unitaires**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/ -q --tb=no 2>&1 | tail -5
```
Attendu : aucune régression (seuls les 9 échecs pré-existants tolérés).

- [ ] **Step 2 : Lint global M18**

```bash
cd /workspaces/admin-rag/backend && uv run ruff check \
  src/rag/db/workspace_structured.py src/rag/indexer/real.py \
  src/rag/db/mcp_tools.py src/rag/api/mcp_standard.py && echo "lint OK"
```

- [ ] **Step 3 : Résidu git**

```bash
git status
# commiter tout ce qui reste non commité
```

---

## Self-Review

**Spec coverage :**
- [x] `_WsCtx` étendu → déjà fait en M17
- [x] `index_status()` + `index_status(path)` → Task 2
- [x] `search_files` exact/substring/regex, dédup path → Task 3
- [x] `sections.section_index` migration + backfill + real.py → Task 1
- [x] `get_document` reconstruit depuis sections ORDER BY section_index, fallback legacy → Task 4
- [x] `allow_full_read` migration + refus propre dans `get_document` → Tasks 1 + 4
- [x] `source_path` réel si M17 livré (il l'est) → `search_files` lit la metadata
- [ ] Context7 FastMCP : non invoqué (l'API FastMCP existante est stable, les outils M17 suivent le même pattern)

**Décisions fermées :**
- Option A (reconstruct) pour `get_document` ✓
- `section_index` via `enumerate(doc.parents)` dans `real.py` (pas dans les chunkers) ✓
- `healthy` = dernier job ≠ `error`, None = True ✓
- `search_files` non soumis à `allow_full_read` (snippets) ✓

**Type consistency :**
- `reconstruct_document(ws_pool, config_pool, *, workspace_id, path)` → T4 ✓
- `search_files_in_workspace(ws_pool, *, pattern, mode, top_k)` → T3 ✓
- `get_index_status(config_pool, *, workspace_id)` → T2 ✓
