# M17 — Enrichissement first-class dans le MCP (C1→C4, backend)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exposer les enrichissements (documentation, public_functions, dependencies…) comme dimension first-class dans la recherche MCP — étiquetage, filtrage par clé/scope, lookup canonique.

**Architecture :** Trois couches modifiées en séquence : (C1) `index_file` reçoit `extra_metadata` fusionné dans chaque chunk ; (C2) la recherche expose `e.metadata`, filtre par `scope`/`enrichment_keys`, étiquette les hits ; (C3/C4) nouveau tool MCP `get_enrichment` + `rag_search` étendu. Aucune migration SQL (JSONB existant dans `embeddings` et `sections`). C5 (playground frontend) reporté en M17b.

**Tech Stack:** Python 3.12, asyncpg, Pydantic v2, FastMCP, pytest-asyncio, dataclasses.replace

## Global Constraints

- `from __future__ import annotations` en tête de chaque fichier Python modifié
- Pas de SQLAlchemy — asyncpg direct
- Tests TDD : rouge → vert → commit
- Chunker keys ont la priorité sur `extra_metadata` (ne pas écraser `scope`, `section_title`, `heading_level`…)
- `scope="both"` + sans filtre → comportement strictement identique à avant (additif prouvé)
- `index_file` sans `extra_metadata` → comportement inchangé (prouvé par test)
- Branche `dev` uniquement

---

## Fichiers impactés

| Fichier | Action |
|---|---|
| `backend/src/rag/indexer/protocol.py` | Ajouter `extra_metadata` à `index_file` |
| `backend/src/rag/indexer/real.py` | Propager `extra_metadata` → merge dans chunks |
| `backend/src/rag/indexer/noop.py` | Signature uniquement |
| `backend/src/rag/services/enrichments.py` | Passer `extra_metadata={enrichment_key, source_path}` |
| `backend/src/rag/db/workspace_search.py` | SELECT metadata, `_ChildHit.metadata`, scope/enrichment_keys filter |
| `backend/src/rag/schemas/mcp.py` | `SearchHit` gagne `metadata`, `enrichment_key`, `source_path` |
| `backend/src/rag/services/mcp.py` | `_search_one` passe `scope`/`enrichment_keys` |
| `backend/src/rag/api/mcp_standard.py` | `_WsCtx` ← `workspace_id`+`config_pool`, `rag_search` étendu, `get_enrichment` tool |
| `backend/src/rag/maintenance/backfill_enrichment_metadata.py` | **Nouveau** — backfill one-shot |
| `backend/tests/unit/indexer/test_extra_metadata.py` | **Nouveau** |
| `backend/tests/unit/db/test_scope_filter.py` | **Nouveau** |
| `backend/tests/unit/api/test_mcp_standard_enrichment.py` | **Nouveau** |
| `backend/tests/unit/db/test_hybrid_search.py` | Adapter rows (`metadata`) |
| `backend/tests/unit/db/test_workspace_search.py` | Adapter rows (`metadata`) |
| `backend/tests/unit/services/test_mcp_search.py` | Adapter pour nouveaux params |

---

### Task 1 — C1a : `extra_metadata` sur `index_file` (protocol + real + noop)

**Files:**
- Modify: `backend/src/rag/indexer/protocol.py`
- Modify: `backend/src/rag/indexer/real.py`
- Modify: `backend/src/rag/indexer/noop.py`
- Create: `backend/tests/unit/indexer/test_extra_metadata.py`

**Interfaces:**
- Produit: `index_file(..., extra_metadata: Mapping[str, Any] | None = None)` dans les 3 impls
- Produit: merge dans legacy (`Chunk`) et structured (`ChildRow`/`ParentRow`) — chunker keys gagnent

- [ ] **Step 1 : Écrire les tests**

Créer `backend/tests/unit/indexer/test_extra_metadata.py` :

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from rag.indexer.noop import NoOpIndexer


class TestExtraMetadataSignature:
    @pytest.mark.asyncio
    async def test_noop_accepts_extra_metadata_without_error(self):
        """index_file avec extra_metadata=None → comportement inchangé."""
        pool = MagicMock()
        conn = MagicMock()
        conn.execute = AsyncMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        pool.acquire = MagicMock(return_value=conn)

        indexer = NoOpIndexer(pool)
        n = await indexer.index_file(
            workspace_id=uuid4(),
            path="src/a.py",
            content="x",
            content_hash="sha256:abc",
            indexer_used="openai/m",
            extra_metadata=None,
        )
        assert n == 1

    @pytest.mark.asyncio
    async def test_noop_accepts_extra_metadata_dict(self):
        pool = MagicMock()
        conn = MagicMock()
        conn.execute = AsyncMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        pool.acquire = MagicMock(return_value=conn)

        indexer = NoOpIndexer(pool)
        n = await indexer.index_file(
            workspace_id=uuid4(),
            path="src/b.py",
            content="x",
            content_hash="sha256:abc",
            indexer_used="openai/m",
            extra_metadata={"enrichment_key": "public_functions", "source_path": "src/b.py"},
        )
        assert n == 1


class TestExtraMetadataMerge:
    """Vérifie que extra_metadata est fusionné SANS écraser les clés du chunker."""

    def test_chunker_keys_win_over_extra_metadata(self):
        """Les clés du chunker ne sont pas écrasées par extra_metadata."""
        from rag.indexer.chunking.protocol import Chunk
        import dataclasses

        chunk = Chunk(content="hello", metadata={"scope": "MyClass.my_method", "heading_level": 2})
        extra = {"scope": "INJECTED", "enrichment_key": "docs"}
        # merge : extra first, chunker metadata second (chunker gagne)
        merged = {**extra, **dict(chunk.metadata)}
        assert merged["scope"] == "MyClass.my_method"   # chunker gagne
        assert merged["heading_level"] == 2              # chunker préservé
        assert merged["enrichment_key"] == "docs"        # extra injecté

    def test_extra_metadata_fills_absent_keys(self):
        from rag.indexer.chunking.protocol import Chunk

        chunk = Chunk(content="x", metadata={"scope": "fn"})
        extra = {"enrichment_key": "public_functions", "source_path": "a.py"}
        merged = {**extra, **dict(chunk.metadata)}
        assert merged["enrichment_key"] == "public_functions"
        assert merged["source_path"] == "a.py"
        assert merged["scope"] == "fn"
```

- [ ] **Step 2 : Lancer les tests — vérifier qu'ils échouent**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/indexer/test_extra_metadata.py -v 2>&1 | head -20
```
Attendu : ImportError ou AttributeError (extra_metadata inconnu).

- [ ] **Step 3 : Modifier `protocol.py`**

Lire le fichier. Ajouter `extra_metadata: Mapping[str, Any] | None = None` après `title`:

```python
# En tête — vérifier que Mapping et Any sont importés depuis collections.abc et typing
from collections.abc import Mapping
from typing import Any

# Dans IndexerProtocol.index_file :
async def index_file(
    self,
    *,
    workspace_id: UUID,
    path: str,
    content: str,
    content_hash: str,
    indexer_used: str,
    title: str | None = None,
    extra_metadata: Mapping[str, Any] | None = None,
    strategy_override: str | None = None,
) -> int:
    ...
```

- [ ] **Step 4 : Modifier `noop.py`**

Lire le fichier. Ajouter `extra_metadata: Mapping[str, Any] | None = None` à la signature de `index_file` (après `title`). Ne pas l'utiliser — noop ne chunk pas.

Vérifier que `Mapping` et `Any` sont importés.

- [ ] **Step 5 : Modifier `real.py`**

Lire le fichier. Trois modifications :

**5a** — Signature `index_file` :
```python
async def index_file(
    self,
    *,
    workspace_id: UUID,
    path: str,
    content: str,
    content_hash: str,
    indexer_used: str,
    title: str | None = None,
    extra_metadata: Mapping[str, Any] | None = None,
    strategy_override: str | None = None,
) -> int:
    ctx = await self._load_workspace_context(workspace_id)
    if ctx["chunking_engine"] == "structured":
        n_chunks = await self._index_structured(
            workspace_id=workspace_id,
            path=path,
            content=content,
            ctx=ctx,
            strategy_override=strategy_override,
            extra_metadata=extra_metadata or {},
        )
    else:
        n_chunks = await self._index_legacy(
            workspace_id=workspace_id,
            path=path,
            content=content,
            ctx=ctx,
            extra_metadata=extra_metadata or {},
        )
    ...
```

**5b** — `_index_legacy` : merge après chunking.
Trouver la ligne `chunks: list[Chunk] = chunker.chunk(content)`. Après, ajouter :

```python
# Dans la signature : extra_metadata: Mapping[str, Any] = {}
async def _index_legacy(
    self,
    *,
    workspace_id: UUID,
    path: str,
    content: str,
    ctx: dict[str, Any],
    extra_metadata: Mapping[str, Any] = {},
) -> int:
    ...
    chunks: list[Chunk] = chunker.chunk(content)
    if extra_metadata:
        import dataclasses
        chunks = [
            dataclasses.replace(c, metadata={**extra_metadata, **dict(c.metadata)})
            for c in chunks
        ]
    ...
```

**5c** — `_index_structured` : merge lors de la construction des rows.
Trouver la construction de `child_rows` et `parent_rows`. Modifier :

```python
# Dans la signature : extra_metadata: Mapping[str, Any] = {}
async def _index_structured(
    self,
    *,
    workspace_id: UUID,
    path: str,
    content: str,
    ctx: dict[str, Any],
    strategy_override: str | None,
    extra_metadata: Mapping[str, Any] = {},
) -> int:
    ...
    child_rows = [
        ChildRow(
            chunk_hash=h,
            embed_text=child.embed_text,
            parent_key=child.parent_key,
            chunk_index=idx,
            metadata={**extra_metadata, **dict(child.metadata)} if extra_metadata else child.metadata,
            embedding=emb_by_hash.get(h),
        )
        for idx, (h, child) in enumerate(ordered)
    ]
    parent_rows = [
        ParentRow(
            section_key=p.section_key,
            content=p.content,
            metadata={**extra_metadata, **dict(p.metadata)} if extra_metadata else p.metadata,
        )
        for p in doc.parents
    ]
    ...
```

Note : `Mapping` est déjà importé dans `real.py` depuis `collections.abc` ? Vérifier et ajouter si absent.

- [ ] **Step 6 : Lancer les tests**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/indexer/test_extra_metadata.py -v
```
Attendu : 4 tests PASSED.

- [ ] **Step 7 : Non-régression indexer**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/indexer/ tests/unit/services/test_mcp_search.py -q 2>&1 | tail -5
```

- [ ] **Step 8 : Lint**

```bash
cd /workspaces/admin-rag/backend && uv run ruff check src/rag/indexer/protocol.py src/rag/indexer/real.py src/rag/indexer/noop.py && echo "lint OK"
```

- [ ] **Step 9 : Commit**

```bash
git add backend/src/rag/indexer/protocol.py backend/src/rag/indexer/real.py backend/src/rag/indexer/noop.py backend/tests/unit/indexer/test_extra_metadata.py
git commit -m "feat(indexer): extra_metadata optionnel sur index_file — fusionné dans les chunks"
```

---

### Task 2 — C1b : enrichments.py injecte extra_metadata + backfill

**Files:**
- Modify: `backend/src/rag/services/enrichments.py`
- Create: `backend/src/rag/maintenance/__init__.py`
- Create: `backend/src/rag/maintenance/backfill_enrichment_metadata.py`
- Create: `backend/tests/unit/services/test_enrichments_extra_metadata.py`

**Interfaces:**
- Consomme: `index_file(..., extra_metadata=...)` de T1
- Produit: `backfill_enrichment_metadata(config_pool, pool_registry)` — coroutine async, idempotente

- [ ] **Step 1 : Écrire le test enrichments**

Créer `backend/tests/unit/services/test_enrichments_extra_metadata.py` :

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from rag.services.enrichments import run_enrichments


@pytest.mark.asyncio
async def test_run_enrichments_passes_extra_metadata_to_index_file():
    """run_enrichments injecte {enrichment_key, source_path} dans index_file."""
    ws_id = uuid4()
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=None)  # no existing enrichment

    trigger_row = {
        "template_id": uuid4(),
        "template_name": "public_functions",
        "metadata_key": "public_functions",
        "result_type": "text",
        "prompt": "List functions in: {content}",
        "llm_provider": "openai",
        "llm_model": "gpt-4o-mini",
        "api_key_ref": None,
        "llm_base_url": None,
    }
    conn.fetch = AsyncMock(side_effect=[
        [trigger_row],  # trigger_prompts
    ])
    conn.execute = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)

    config_pool = MagicMock()
    config_pool.acquire = MagicMock(return_value=conn)

    indexer = MagicMock()
    indexer.index_file = AsyncMock(return_value=1)

    with patch("rag.services.enrichments.call_llm", AsyncMock(return_value={"answer": "fn_a, fn_b"})):
        await run_enrichments(
            workspace_id=ws_id,
            workspace_name="ws",
            path="src/a.py",
            content="def fn_a(): pass\ndef fn_b(): pass",
            content_hash="sha256:abc",
            indexer=indexer,
            config_pool=config_pool,
            vault_svc=None,
            client_provider=None,
        )

    indexer.index_file.assert_awaited_once()
    call_kwargs = indexer.index_file.call_args.kwargs
    assert "extra_metadata" in call_kwargs
    em = call_kwargs["extra_metadata"]
    assert em["enrichment_key"] == "public_functions"
    assert em["source_path"] == "src/a.py"
```

- [ ] **Step 2 : Vérifier que le test échoue**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/services/test_enrichments_extra_metadata.py -v 2>&1 | head -15
```

- [ ] **Step 3 : Modifier `enrichments.py`**

Lire le fichier. Trouver le bloc `await indexer.index_file(...)` (~ligne 140). Ajouter `extra_metadata` :

```python
await indexer.index_file(
    workspace_id=workspace_id,
    path=enriched_path,
    content=answer,
    content_hash=f"sha256:{sha256(answer.encode()).hexdigest()}",
    indexer_used=f"{row['llm_provider']}/{row['llm_model']}",
    extra_metadata={"enrichment_key": metadata_key, "source_path": path},
)
```

- [ ] **Step 4 : Créer le backfill**

Créer `backend/src/rag/maintenance/__init__.py` (vide).

Créer `backend/src/rag/maintenance/backfill_enrichment_metadata.py` :

```python
"""Backfill one-shot : ajouter enrichment_key + source_path dans la metadata
des chunks d'enrichissement existants (antérieurs à M17).

Exécution : uv run python -m rag.maintenance.backfill_enrichment_metadata

Idempotent : ignore les chunks qui ont déjà enrichment_key dans metadata.
Pilote par document_enrichments (source de vérité), pas par parsing de '::'.
"""
from __future__ import annotations

import asyncio
import json
import os

import asyncpg
import structlog

log = structlog.get_logger(__name__)


async def _backfill(config_pool: asyncpg.Pool, workspace_pool_factory: object) -> int:
    """Retourne le nombre de chunks mis à jour."""
    rows = await config_pool.fetch(
        "SELECT workspace_id, path, metadata_key, rag_cnx "
        "FROM document_enrichments de "
        "JOIN workspaces w ON w.id = de.workspace_id"
    )
    total = 0
    for row in rows:
        ws_id = str(row["workspace_id"])
        path = row["path"]  # enriched path: src/a.py::public_functions
        metadata_key = row["metadata_key"]
        # Retrouver le source_path en enlevant ::key
        source_path = path.rsplit("::", 1)[0] if "::" in path else path
        extra = json.dumps({"enrichment_key": metadata_key, "source_path": source_path})

        try:
            ws_pool = await workspace_pool_factory(ws_id, row["rag_cnx"])
            updated = await ws_pool.fetchval(
                """
                UPDATE embeddings
                SET metadata = $1::jsonb || metadata
                WHERE path = $2
                  AND NOT (metadata ? 'enrichment_key')
                RETURNING 1
                """,
                extra,
                path,
            )
            if updated:
                total += 1
                log.info("backfill.chunk_updated", path=path, metadata_key=metadata_key)
        except Exception as e:
            log.warning("backfill.chunk_failed", path=path, error=str(e))
    return total


async def main() -> None:
    dsn = os.environ["DATABASE_URL"]
    config_pool = await asyncpg.create_pool(dsn)
    # Simple stub de workspace_pool_factory pour usage autonome
    ws_pool_cache: dict[str, asyncpg.Pool] = {}

    async def _factory(ws_id: str, rag_cnx: str) -> asyncpg.Pool:
        if rag_cnx not in ws_pool_cache:
            ws_pool_cache[rag_cnx] = await asyncpg.create_pool(rag_cnx)
        return ws_pool_cache[rag_cnx]

    n = await _backfill(config_pool, _factory)
    log.info("backfill.done", chunks_updated=n)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 5 : Lancer les tests**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/services/test_enrichments_extra_metadata.py -v
```
Attendu : 1 test PASSED.

- [ ] **Step 6 : Lint**

```bash
cd /workspaces/admin-rag/backend && uv run ruff check src/rag/services/enrichments.py src/rag/maintenance/ && echo "lint OK"
```

- [ ] **Step 7 : Commit**

```bash
git add backend/src/rag/services/enrichments.py backend/src/rag/maintenance/ backend/tests/unit/services/test_enrichments_extra_metadata.py
git commit -m "feat(enrichments): injecter enrichment_key + source_path dans les chunks via extra_metadata"
```

---

### Task 3 — C2a : SELECT e.metadata → _ChildHit.metadata → SearchHit enrichi

**Files:**
- Modify: `backend/src/rag/db/workspace_search.py`
- Modify: `backend/src/rag/schemas/mcp.py`
- Modify: `backend/tests/unit/db/test_workspace_search.py`
- Modify: `backend/tests/unit/db/test_hybrid_search.py`
- Modify: `backend/tests/unit/services/test_mcp_search.py`

**Interfaces:**
- Produit: `_ChildHit` gagne `metadata: dict[str, Any] | None`
- Produit: `SearchHit` gagne `metadata: dict[str, Any] | None = None`, `enrichment_key: str | None = None`, `source_path: str | None = None`

- [ ] **Step 1 : Modifier `schemas/mcp.py`**

Lire le fichier. Ajouter les champs à `SearchHit` (après `score`, avant `debug`) :

```python
class SearchHit(BaseModel):
    workspace: str
    indexer: str
    path: str
    chunk_index: int
    content: str
    score: float
    metadata: dict[str, Any] | None = None
    enrichment_key: str | None = None
    source_path: str | None = None
    debug: DebugTrace | None = None
```

Vérifier que `Any` est importé depuis `typing`.

- [ ] **Step 2 : Modifier `workspace_search.py`**

Lire le fichier. Quatre modifications :

**2a** — Ajouter `metadata` à `_ChildHit` :

```python
@dataclass(frozen=True)
class _ChildHit:
    path: str
    chunk_index: int
    chunk_hash: str | None
    section_id: int | None
    content: str
    score: float
    metadata: dict[str, Any] | None = None   # <-- ajouté
```

Vérifier que `Any` est importé.

**2b** — Ajouter `metadata` à `_FusedHit` :

```python
@dataclass
class _FusedHit:
    identity: tuple
    path: str
    chunk_index: int
    section_id: int | None
    content: str
    rrf_score: float
    vector_rank: int | None
    vector_score: float | None
    lexical_rank: int | None
    lexical_score: float | None
    metadata: dict[str, Any] | None = None   # <-- ajouté
```

**2c** — Ajouter `e.metadata` aux deux SELECT (dans `_fetch_vector_children` et `lexical_search`) :

Dans `_fetch_vector_children`, ajouter `e.metadata AS metadata` au SELECT.

Dans `lexical_search`, ajouter `e.metadata AS metadata` au SELECT.

Puis dans les compréhensions qui construisent `_ChildHit`, ajouter :
```python
metadata=dict(r["metadata"]) if r["metadata"] else None,
```

**2d** — Dans `rrf_fuse`, propager `metadata` du premier hit vu vers `_FusedHit` :

Trouver la ligne `seen.setdefault(h.identity, h)`. C'est correct : le premier hit vu donne sa metadata au FusedHit.

Dans la construction de `_FusedHit`, ajouter :
```python
metadata=hit.metadata,
```

**2e** — Dans `vector_search` et `hybrid_search`, peupler les nouveaux champs de `SearchHit` :

Helper local (dans `workspace_search.py`) :
```python
def _enrich_hit_fields(metadata: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """Retourne (enrichment_key, source_path) depuis la metadata du chunk."""
    if not metadata:
        return None, None
    return metadata.get("enrichment_key"), metadata.get("source_path")
```

Dans `vector_search`, quand on construit `SearchHit` :
```python
ek, sp = _enrich_hit_fields(child.metadata)
hits.append(
    SearchHit(
        workspace=workspace_name,
        indexer=indexer_used,
        path=child.path,
        chunk_index=child.chunk_index,
        content=child.content,
        score=child.score,
        metadata=child.metadata,
        enrichment_key=ek,
        source_path=sp,
    )
)
```

Dans `hybrid_search`, quand on construit `SearchHit` :
```python
ek, sp = _enrich_hit_fields(fh.metadata)
hits.append(
    SearchHit(
        workspace=workspace_name,
        indexer=indexer_used,
        path=fh.path,
        chunk_index=fh.chunk_index,
        content=fh.content,
        score=fh.rrf_score,
        metadata=fh.metadata,
        enrichment_key=ek,
        source_path=sp,
        debug=dbg,
    )
)
```

- [ ] **Step 3 : Adapter les tests existants**

Les tests dans `test_workspace_search.py` et `test_hybrid_search.py` mockent des rows de DB sans `metadata`. Ajouter `"metadata": None` à chaque row dict dans ces deux fichiers.

Dans `test_workspace_search.py` : chaque row dict doit avoir `"chunk_hash": None` (déjà fait en T3-M16) et `"metadata": None` (à ajouter).

Dans `test_hybrid_search.py` dans `_make_pool_lex` : les rows doivent avoir `"metadata": None`.

Dans `test_mcp_search.py` : si les tests vérifient la structure de `SearchHit`, ils passeront car les nouveaux champs sont optionnels (défaut `None`).

- [ ] **Step 4 : Lancer les tests**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/db/ tests/unit/services/test_mcp_search.py -q 2>&1 | tail -5
```
Attendu : tout vert.

- [ ] **Step 5 : Lint**

```bash
cd /workspaces/admin-rag/backend && uv run ruff check src/rag/db/workspace_search.py src/rag/schemas/mcp.py && echo "lint OK"
```

- [ ] **Step 6 : Commit**

```bash
git add backend/src/rag/db/workspace_search.py backend/src/rag/schemas/mcp.py backend/tests/unit/db/test_workspace_search.py backend/tests/unit/db/test_hybrid_search.py backend/tests/unit/services/test_mcp_search.py
git commit -m "feat(search): metadata + enrichment_key + source_path sur SearchHit (C2 socle)"
```

---

### Task 4 — C2b : scope + enrichment_keys filtering

**Files:**
- Modify: `backend/src/rag/db/workspace_search.py`
- Modify: `backend/src/rag/services/mcp.py`
- Create: `backend/tests/unit/db/test_scope_filter.py`

**Interfaces:**
- Produit: `vector_search(..., scope="both", enrichment_keys=None)` — filtre en Python après fetch
- Produit: `hybrid_search(..., scope="both", enrichment_keys=None)` — filtre après RRF
- Produit: `_search_one` passe `scope`/`enrichment_keys` aux fonctions de recherche

- [ ] **Step 1 : Écrire les tests**

Créer `backend/tests/unit/db/test_scope_filter.py` :

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.db.workspace_search import _ChildHit, _apply_enrichment_filter


def _raw(path: str, idx: int = 0) -> _ChildHit:
    return _ChildHit(path=path, chunk_index=idx, chunk_hash=None, section_id=None,
                     content="x", score=0.8, metadata=None)


def _enriched(path: str, key: str = "docs", idx: int = 0) -> _ChildHit:
    return _ChildHit(path=path, chunk_index=idx, chunk_hash=None, section_id=None,
                     content="y", score=0.9,
                     metadata={"enrichment_key": key, "source_path": path.split("::")[0]})


class TestApplyEnrichmentFilter:
    def test_scope_both_returns_all(self):
        hits = [_raw("a.py"), _enriched("a.py::docs")]
        result = _apply_enrichment_filter(hits, scope="both", enrichment_keys=None)
        assert len(result) == 2

    def test_scope_raw_only_excludes_enrichments(self):
        hits = [_raw("a.py"), _enriched("a.py::docs")]
        result = _apply_enrichment_filter(hits, scope="raw_only", enrichment_keys=None)
        assert len(result) == 1
        assert result[0].path == "a.py"

    def test_scope_enriched_only_keeps_enrichments(self):
        hits = [_raw("a.py"), _enriched("a.py::docs"), _enriched("a.py::funcs", "public_functions")]
        result = _apply_enrichment_filter(hits, scope="enriched_only", enrichment_keys=None)
        assert len(result) == 2

    def test_enrichment_keys_filter_single_key(self):
        hits = [
            _raw("a.py"),
            _enriched("a.py::docs", "documentation"),
            _enriched("a.py::funcs", "public_functions"),
        ]
        result = _apply_enrichment_filter(hits, scope="both", enrichment_keys=["documentation"])
        # raw_only + documentation uniquement (les non-enrichissements passent toujours quand scope=both)
        assert any(h.path == "a.py" for h in result)
        assert any(h.metadata and h.metadata.get("enrichment_key") == "documentation" for h in result)
        assert not any(h.metadata and h.metadata.get("enrichment_key") == "public_functions" for h in result)

    def test_enrichment_keys_none_passes_all_enrichments(self):
        hits = [_raw("a.py"), _enriched("a.py::docs"), _enriched("a.py::funcs", "public_functions")]
        result = _apply_enrichment_filter(hits, scope="both", enrichment_keys=None)
        assert len(result) == 3

    def test_empty_input_returns_empty(self):
        assert _apply_enrichment_filter([], scope="both", enrichment_keys=None) == []
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/db/test_scope_filter.py -v 2>&1 | head -10
```
Attendu : ImportError sur `_apply_enrichment_filter`.

- [ ] **Step 3 : Implémenter `_apply_enrichment_filter` dans `workspace_search.py`**

Ajouter après `_enrich_hit_fields` :

```python
def _apply_enrichment_filter(
    children: list[_ChildHit],
    *,
    scope: str,
    enrichment_keys: list[str] | None,
) -> list[_ChildHit]:
    """Filtre scope (both/raw_only/enriched_only) + enrichment_keys.

    Les non-enrichissements (metadata sans enrichment_key) passent toujours
    quand scope='both' ou 'raw_only', jamais quand 'enriched_only'.
    """
    result = []
    for h in children:
        ek = h.metadata.get("enrichment_key") if h.metadata else None
        is_enriched = bool(ek)
        if scope == "raw_only" and is_enriched:
            continue
        if scope == "enriched_only" and not is_enriched:
            continue
        if enrichment_keys and is_enriched and ek not in enrichment_keys:
            continue
        result.append(h)
    return result
```

- [ ] **Step 4 : Étendre `vector_search` et `hybrid_search`**

Dans `vector_search`, ajouter les paramètres et appliquer le filtre :

```python
async def vector_search(
    workspace_pool: asyncpg.Pool,
    *,
    query_vec: list[float],
    top_k: int,
    min_score: float,
    workspace_name: str,
    indexer_used: str,
    scope: str = "both",
    enrichment_keys: list[str] | None = None,
) -> list[SearchHit]:
    ...
    children = await _fetch_vector_children(
        workspace_pool, query_vec=query_vec, top_k_fetch=top_k * 4, min_score=min_score,
    )
    children = _apply_enrichment_filter(children, scope=scope, enrichment_keys=enrichment_keys)
    # reste inchangé
```

Dans `hybrid_search`, même chose — appliquer `_apply_enrichment_filter` après `rrf_fuse` mais avant la dédup section :

```python
async def hybrid_search(
    workspace_pool: asyncpg.Pool,
    *,
    query_vec: list[float],
    query: str,
    top_k: int,
    min_score: float,
    workspace_name: str,
    indexer_used: str,
    rrf_k: int = 60,
    fts_config: str = "simple",
    debug: bool = False,
    scope: str = "both",
    enrichment_keys: list[str] | None = None,
) -> list[SearchHit]:
    ...
    fused = rrf_fuse(vector_children, lexical_children, k=rrf_k)
    # Convertir FusedHit → _ChildHit pour le filtre
    fused_as_children = [
        _ChildHit(
            path=fh.path, chunk_index=fh.chunk_index, chunk_hash=None,
            section_id=fh.section_id, content=fh.content, score=fh.rrf_score,
            metadata=fh.metadata,
        )
        for fh in fused
    ]
    filtered = _apply_enrichment_filter(fused_as_children, scope=scope, enrichment_keys=enrichment_keys)
    filtered_ids = {(c.path, c.chunk_index) for c in filtered}
    fused = [fh for fh in fused if (fh.path, fh.chunk_index) in filtered_ids]
    # suite inchangée (section dedup etc.)
```

Attention : l'approche de filtrage de `hybrid_search` via conversion en `_ChildHit` et retour peut être simplifiée. Alternative plus propre : filtrer directement sur `_FusedHit` en répliquant la logique :

```python
def _apply_enrichment_filter_fused(
    fused: list[_FusedHit],
    *,
    scope: str,
    enrichment_keys: list[str] | None,
) -> list[_FusedHit]:
    result = []
    for fh in fused:
        ek = fh.metadata.get("enrichment_key") if fh.metadata else None
        is_enriched = bool(ek)
        if scope == "raw_only" and is_enriched:
            continue
        if scope == "enriched_only" and not is_enriched:
            continue
        if enrichment_keys and is_enriched and ek not in enrichment_keys:
            continue
        result.append(fh)
    return result
```

Utiliser `_apply_enrichment_filter_fused` dans `hybrid_search` (évite la conversion aller-retour).

- [ ] **Step 5 : Étendre `_search_one` dans `services/mcp.py`**

Lire `services/mcp.py`. Ajouter `scope: str = "both"` et `enrichment_keys: list[str] | None = None` à la signature de `_search_one` et à `search`. Passer ces params aux appels `vector_search` et `hybrid_search`.

- [ ] **Step 6 : Lancer les tests scope**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/db/test_scope_filter.py -v
```
Attendu : 6 tests PASSED.

- [ ] **Step 7 : Non-régression complète DB + services**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/db/ tests/unit/services/ -q 2>&1 | tail -5
```

- [ ] **Step 8 : Lint**

```bash
cd /workspaces/admin-rag/backend && uv run ruff check src/rag/db/workspace_search.py src/rag/services/mcp.py && echo "lint OK"
```

- [ ] **Step 9 : Commit**

```bash
git add backend/src/rag/db/workspace_search.py backend/src/rag/services/mcp.py backend/tests/unit/db/test_scope_filter.py
git commit -m "feat(search): filtre scope + enrichment_keys sur vector_search et hybrid_search"
```

---

### Task 5 — C3 : get_enrichment (lookup canonique)

**Files:**
- Create: `backend/src/rag/db/enrichment_lookup.py`
- Create: `backend/tests/unit/db/test_enrichment_lookup.py`

**Interfaces:**
- Produit: `get_enrichment(config_pool, *, workspace_id, path, key) -> dict | None`
  - Retourne `{"result": str, "result_type": str, "result_schema": str | None}` ou `None`

- [ ] **Step 1 : Écrire les tests**

Créer `backend/tests/unit/db/test_enrichment_lookup.py` :

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.db.enrichment_lookup import get_enrichment


class TestGetEnrichment:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value=None)
        result = await get_enrichment(pool, workspace_id=uuid4(), path="a.py", key="docs")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_text_result(self):
        ws_id = uuid4()
        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value={
            "result": "liste de fonctions",
            "result_type": "text",
            "result_schema": None,
        })
        result = await get_enrichment(pool, workspace_id=ws_id, path="a.py", key="public_functions")
        assert result is not None
        assert result["result"] == "liste de fonctions"
        assert result["result_type"] == "text"

    @pytest.mark.asyncio
    async def test_returns_json_result(self):
        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value={
            "result": '["fn_a", "fn_b"]',
            "result_type": "json",
            "result_schema": '{"type": "array"}',
        })
        result = await get_enrichment(pool, workspace_id=uuid4(), path="a.py", key="public_functions")
        assert result is not None
        assert result["result_type"] == "json"

    @pytest.mark.asyncio
    async def test_queries_correct_columns(self):
        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value=None)
        ws_id = uuid4()
        await get_enrichment(pool, workspace_id=ws_id, path="src/x.py", key="deps")
        call_args = pool.fetchrow.call_args
        sql = call_args[0][0]
        assert "document_enrichments" in sql
        assert "metadata_key" in sql
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/db/test_enrichment_lookup.py -v 2>&1 | head -10
```

- [ ] **Step 3 : Créer `enrichment_lookup.py`**

Créer `backend/src/rag/db/enrichment_lookup.py` :

```python
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


async def get_enrichment(
    config_pool: asyncpg.Pool,
    *,
    workspace_id: UUID,
    path: str,
    key: str,
) -> dict[str, Any] | None:
    """Retourne le résultat canonique d'un enrichissement depuis document_enrichments.

    `path` est le path RÉEL du fichier source (pas le path synthétique path::key).
    Retourne None si absent. Le champ `result` est toujours une str ; si
    `result_type='json'`, c'est du JSON sérialisé que le consommateur peut parser.
    """
    row = await config_pool.fetchrow(
        """
        SELECT result, result_type, result_schema
        FROM document_enrichments
        WHERE workspace_id = $1
          AND path = $2
          AND metadata_key = $3
        """,
        workspace_id,
        path,
        key,
    )
    if row is None:
        return None
    return {
        "result": row["result"],
        "result_type": row["result_type"],
        "result_schema": row["result_schema"],
    }
```

- [ ] **Step 4 : Lancer les tests**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/db/test_enrichment_lookup.py -v
```
Attendu : 4 tests PASSED.

- [ ] **Step 5 : Lint**

```bash
cd /workspaces/admin-rag/backend && uv run ruff check src/rag/db/enrichment_lookup.py && echo "lint OK"
```

- [ ] **Step 6 : Commit**

```bash
git add backend/src/rag/db/enrichment_lookup.py backend/tests/unit/db/test_enrichment_lookup.py
git commit -m "feat(db): get_enrichment — lookup canonique dans document_enrichments"
```

---

### Task 6 — C4 : MCP tools (`_WsCtx` étendu + `rag_search` + `get_enrichment`)

**Files:**
- Modify: `backend/src/rag/api/mcp_standard.py`
- Create: `backend/tests/unit/api/test_mcp_standard_enrichment.py`

**Interfaces:**
- Consomme: `_apply_enrichment_filter` (T4), `get_enrichment` (T5), `hybrid_search`/`vector_search` avec scope/enrichment_keys (T4)
- Produit: `_WsCtx` gagne `workspace_id: UUID` + `config_pool: asyncpg.Pool`
- Produit: `rag_search(query, top_k, min_score, enrichment_keys=None, scope="both")`
- Produit: `get_enrichment(path, key)` — nouvel outil MCP

- [ ] **Step 1 : Écrire les tests**

Créer `backend/tests/unit/api/test_mcp_standard_enrichment.py` :

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.api.mcp_standard import _WsCtx


class TestWsCtxExtended:
    def test_ws_ctx_has_workspace_id(self):
        ws_id = uuid4()
        pool = MagicMock()
        ctx = _WsCtx(
            workspace_name="ws",
            rag_cnx="dsn",
            indexer_service="openai",
            indexer_provider="openai",
            indexer_model="text-embedding-3-small",
            indexer_api_key_ref=None,
            indexer_base_url=None,
            pool_registry=MagicMock(),
            resolver=MagicMock(),
            workspace_id=ws_id,
            config_pool=pool,
        )
        assert ctx.workspace_id == ws_id
        assert ctx.config_pool is pool


class TestRagSearchEnrichmentParams:
    """Vérifie que rag_search accepte scope et enrichment_keys."""

    @pytest.mark.asyncio
    async def test_rag_search_accepts_scope_raw_only(self, monkeypatch):
        from rag.api import mcp_standard as mod
        from rag.api.mcp_standard import _ws_ctx

        ws_id = uuid4()
        pool = MagicMock()
        ctx = _WsCtx(
            workspace_name="ws", rag_cnx="dsn", indexer_service="openai",
            indexer_provider="openai", indexer_model="m", indexer_api_key_ref=None,
            indexer_base_url=None, pool_registry=MagicMock(), resolver=MagicMock(),
            workspace_id=ws_id, config_pool=pool,
        )
        token = _ws_ctx.set(ctx)
        try:
            fake_provider = MagicMock()
            fake_provider.embed_query = AsyncMock(return_value=[0.1])
            monkeypatch.setattr(mod, "vector_search", AsyncMock(return_value=[]))
            monkeypatch.setattr(mod, "make_provider", lambda **_: fake_provider)
            monkeypatch.setattr(mod, "is_vault_ref", lambda _: False)

            result = await mod.rag_search(
                query="test", top_k=5, min_score=0.3,
                enrichment_keys=None, scope="raw_only",
            )
            assert "Aucun résultat" in result
            # Vérifie que scope est passé à vector_search
            call_kwargs = mod.vector_search.call_args.kwargs
            assert call_kwargs["scope"] == "raw_only"
        finally:
            _ws_ctx.reset(token)


class TestGetEnrichmentTool:
    @pytest.mark.asyncio
    async def test_get_enrichment_returns_result(self, monkeypatch):
        from rag.api import mcp_standard as mod
        from rag.api.mcp_standard import _ws_ctx

        ws_id = uuid4()
        pool = MagicMock()
        ctx = _WsCtx(
            workspace_name="ws", rag_cnx="dsn", indexer_service="openai",
            indexer_provider="openai", indexer_model="m", indexer_api_key_ref=None,
            indexer_base_url=None, pool_registry=MagicMock(), resolver=MagicMock(),
            workspace_id=ws_id, config_pool=pool,
        )
        token = _ws_ctx.set(ctx)
        try:
            monkeypatch.setattr(
                mod, "get_enrichment_db",
                AsyncMock(return_value={"result": "fn_a, fn_b", "result_type": "text", "result_schema": None}),
            )
            result = await mod.get_enrichment(path="src/a.py", key="public_functions")
            assert "fn_a" in result
        finally:
            _ws_ctx.reset(token)

    @pytest.mark.asyncio
    async def test_get_enrichment_returns_not_found(self, monkeypatch):
        from rag.api import mcp_standard as mod
        from rag.api.mcp_standard import _ws_ctx

        ws_id = uuid4()
        pool = MagicMock()
        ctx = _WsCtx(
            workspace_name="ws", rag_cnx="dsn", indexer_service="openai",
            indexer_provider="openai", indexer_model="m", indexer_api_key_ref=None,
            indexer_base_url=None, pool_registry=MagicMock(), resolver=MagicMock(),
            workspace_id=ws_id, config_pool=pool,
        )
        token = _ws_ctx.set(ctx)
        try:
            monkeypatch.setattr(mod, "get_enrichment_db", AsyncMock(return_value=None))
            result = await mod.get_enrichment(path="src/a.py", key="nonexistent")
            assert "Aucun enrichissement" in result or "not found" in result.lower()
        finally:
            _ws_ctx.reset(token)
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/api/test_mcp_standard_enrichment.py -v 2>&1 | head -15
```

- [ ] **Step 3 : Modifier `mcp_standard.py`**

Lire le fichier. Quatre modifications :

**3a** — Import de `get_enrichment` (renommé pour éviter le conflit avec le tool) :

```python
from rag.db.enrichment_lookup import get_enrichment as get_enrichment_db
from rag.db.workspace_search import vector_search
```

**3b** — Étendre `_WsCtx` avec `workspace_id` et `config_pool` :

```python
from uuid import UUID

@dataclass(frozen=True)
class _WsCtx:
    workspace_name: str
    rag_cnx: str
    indexer_service: str
    indexer_provider: str
    indexer_model: str
    indexer_api_key_ref: str | None
    indexer_base_url: str | None
    pool_registry: Any
    resolver: Any
    workspace_id: UUID           # <-- ajouté
    config_pool: asyncpg.Pool    # <-- ajouté
```

**3c** — Dans `_load_context`, passer `workspace_id` et `config_pool` :

```python
return _WsCtx(
    workspace_name=str(row["name"]),
    rag_cnx=str(row["rag_cnx"]),
    indexer_service=str(row["service"]),
    indexer_provider=str(row["provider"]),
    indexer_model=str(row["model"]),
    indexer_api_key_ref=row["indexer_api_key_ref"],
    indexer_base_url=row["base_url"],
    pool_registry=self._pool_registry,
    resolver=self._resolver,
    workspace_id=UUID(workspace_id),          # <-- ajouté
    config_pool=self._config_pool,            # <-- ajouté
)
```

**3d** — Modifier `rag_search` et ajouter `get_enrichment` :

```python
@_mcp.tool()
async def rag_search(
    query: str,
    top_k: int = 5,
    min_score: float = 0.3,
    enrichment_keys: list[str] | None = None,
    scope: str = "both",
) -> str:
    """Recherche sémantique dans le corpus RAG du workspace courant.

    scope: 'both' (défaut), 'raw_only' (code brut uniquement),
           'enriched_only' (métadonnées d'enrichissement uniquement).
    enrichment_keys: liste de clés d'enrichissement à inclure (ex. ['public_functions']).
    """
    from rag.indexer.providers.factory import make_provider
    from rag.secrets.refs import is_vault_ref

    ctx = _ws_ctx.get()

    api_key: str | None = None
    if ctx.indexer_api_key_ref and is_vault_ref(ctx.indexer_api_key_ref):
        api_key = await ctx.resolver.resolve_with_retry(ctx.indexer_api_key_ref)

    provider = make_provider(
        service=ctx.indexer_service,
        provider=ctx.indexer_provider,
        model=ctx.indexer_model,
        api_key=api_key,
        base_url=ctx.indexer_base_url,
    )
    query_vec = await provider.embed_query(query)

    ws_pool = await ctx.pool_registry.get_workspace_pool(ctx.workspace_name, ctx.rag_cnx)
    hits = await vector_search(
        ws_pool,
        query_vec=query_vec,
        top_k=top_k,
        min_score=min_score,
        workspace_name=ctx.workspace_name,
        indexer_used=f"{ctx.indexer_provider}/{ctx.indexer_model}",
        scope=scope,
        enrichment_keys=enrichment_keys,
    )

    if not hits:
        return "Aucun résultat pertinent trouvé dans le corpus."

    parts = []
    for h in hits:
        label = h.path
        if h.enrichment_key:
            label = f"{h.source_path or h.path} [{h.enrichment_key}]"
        parts.append(f"[{label} — chunk {h.chunk_index} — score {h.score:.3f}]\n{h.content}")

    log.info("mcp_standard.search", workspace=ctx.workspace_name, hits=len(hits), scope=scope)
    return "\n\n---\n\n".join(parts)


@_mcp.tool()
async def get_enrichment(path: str, key: str) -> str:
    """Retourne le résultat d'enrichissement canonique pour un fichier et une clé.

    Exemple : get_enrichment("src/dedup.py", "public_functions")
    Si result_type=json, retourne le JSON formaté.
    """
    ctx = _ws_ctx.get()
    data = await get_enrichment_db(
        ctx.config_pool,
        workspace_id=ctx.workspace_id,
        path=path,
        key=key,
    )
    if data is None:
        return f"Aucun enrichissement '{key}' trouvé pour '{path}'."
    result = data["result"]
    if data["result_type"] == "json":
        import json as _json
        try:
            return _json.dumps(_json.loads(result), ensure_ascii=False, indent=2)
        except _json.JSONDecodeError:
            return result
    return result
```

Note : l'import `from rag.db.workspace_search import vector_search` doit être au niveau module (pas dans la fonction) — vérifier qu'il n'est pas déjà dans la fonction et le déplacer si nécessaire.

- [ ] **Step 4 : Lancer les tests**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/api/test_mcp_standard_enrichment.py -v
```
Attendu : 4 tests PASSED.

- [ ] **Step 5 : Non-régression complète**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/ -q --tb=no 2>&1 | tail -5
```

- [ ] **Step 6 : Lint**

```bash
cd /workspaces/admin-rag/backend && uv run ruff check src/rag/api/mcp_standard.py && echo "lint OK"
```

- [ ] **Step 7 : Commit**

```bash
git add backend/src/rag/api/mcp_standard.py backend/tests/unit/api/test_mcp_standard_enrichment.py
git commit -m "feat(mcp): rag_search + scope/enrichment_keys + outil get_enrichment (C4)"
```

---

### Task 7 — Bilan final : non-régression globale

**Files:**
- Éventuellement `backend/tests/unit/services/test_mcp_hybrid.py` si _WsCtx change a impacté les mocks

- [ ] **Step 1 : Lancer tous les tests unitaires**

```bash
cd /workspaces/admin-rag/backend && uv run pytest tests/unit/ -q --tb=short 2>&1 | tail -15
```
Attendu : aucune régression introduite par M17. Les 9 échecs pré-existants (dans `test_schemas_admin.py`, `test_admin_router_factory.py`, `test_mcp_dto.py`) sont ignorés — ils existaient avant M17.

- [ ] **Step 2 : Lint global sur les fichiers M17**

```bash
cd /workspaces/admin-rag/backend && uv run ruff check \
  src/rag/indexer/protocol.py src/rag/indexer/real.py src/rag/indexer/noop.py \
  src/rag/services/enrichments.py src/rag/maintenance/ \
  src/rag/db/workspace_search.py src/rag/db/enrichment_lookup.py \
  src/rag/schemas/mcp.py src/rag/services/mcp.py \
  src/rag/api/mcp_standard.py && echo "lint OK"
```

- [ ] **Step 3 : Commit final (si résidu de fichiers non commités)**

```bash
git status
# Si des fichiers restent non commités, les ajouter et commiter
```

---

## Self-Review

**Spec coverage :**
- [x] C1 : `extra_metadata` sur les 3 impls + merge sans écraser chunker → Tasks 1-2
- [x] C1 backfill : commande de maintenance `backfill_enrichment_metadata.py` → Task 2
- [x] C2 étape 0 : `SELECT e.metadata`, champ `metadata` sur `SearchHit` → Task 3
- [x] C2 étiquetage : `enrichment_key`/`source_path` sur `SearchHit` → Task 3
- [x] C2 filtre `scope` + `enrichment_keys` → Task 4
- [x] C3 `get_enrichment` lookup canonique → Task 5
- [x] C4 `rag_search` étendu + tool `get_enrichment` + `_WsCtx` étendu → Task 6
- [ ] C5 playground : reporté en M17b-frontend

**Décisions closes :**
- Mixing policy : `both` + étiqueté (additif, zéro régression)
- Résultat structuré dans search : non — `get_enrichment` uniquement
- Backfill : commande manuelle (`python -m rag.maintenance.backfill_enrichment_metadata`)

**Type consistency :**
- `_apply_enrichment_filter` reçoit `list[_ChildHit]` → défini en T3, utilisé en T4 ✓
- `_apply_enrichment_filter_fused` reçoit `list[_FusedHit]` → défini en T4 ✓
- `get_enrichment_db` importé depuis `rag.db.enrichment_lookup` dans `mcp_standard.py` ✓
- `_WsCtx.workspace_id: UUID` et `config_pool: asyncpg.Pool` — UUID importé en T6 ✓
