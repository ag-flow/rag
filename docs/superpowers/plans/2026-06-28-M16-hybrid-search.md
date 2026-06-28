# M16 — Recherche hybride (vectoriel + lexical + RRF) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un bras de recherche lexicale (FTS Postgres) en parallèle du vectoriel, fusionner les deux classements via Reciprocal Rank Fusion, et exposer la configuration hybride par workspace.

**Architecture:** `vector_search` est refactorisé pour exposer une couche interne `_fetch_vector_children` (sans dédup). Un nouveau `lexical_search` interroge `embeddings.content_tsv`. `rrf_fuse` (fonction pure) fusionne les deux listes. `hybrid_search` orchestre le tout et renvoie des `SearchHit` enrichis d'une trace de debug optionnelle. Le tout est opt-in par workspace via `hybrid_configs`.

**Tech Stack:** Python 3.12, asyncpg, Postgres FTS (`websearch_to_tsquery`, colonne `GENERATED ALWAYS AS`), pytest-asyncio, FastAPI.

## Global Constraints

- Python 3.12+, `from __future__ import annotations` en tête de chaque fichier
- asyncpg direct, pas de SQLAlchemy
- `structlog.get_logger(__name__)`, jamais `print()`
- Tests : `pytest` + `pytest-asyncio` ; `describe`/`it` via classes, pas de `test_` top-level groupés
- Comportement **strictement inchangé** pour un workspace sans `hybrid_configs` row — prouvé par test
- `rrf_fuse` doit être une **fonction pure** testable sans mock DB
- `debug=True` uniquement depuis le playground, **jamais** depuis le endpoint `/api/mcp` — tester la non-fuite
- `min_score` s'applique au bras vectoriel uniquement
- Branche : `dev` (jamais `main`, jamais `feat/*`)
- Migrations numérotées : config `048_*.sql`, workspace `003_*.sql` (déjà créée)

---

## Cartographie des fichiers

| Fichier | Action | Responsabilité |
|---|---|---|
| `backend/migrations/048_hybrid_configs.sql` | **Créer** | Table `hybrid_configs` config globale |
| `backend/src/rag/db/workspace_migrations/versions/003_hybrid_fts.sql` | **Déjà créé** | Colonne `content_tsv` + GIN index |
| `backend/src/rag/db/workspace_search.py` | **Modifier** | `_ChildHit`, `_FusedHit`, `_fetch_vector_children`, refactor `vector_search`, `lexical_search`, `rrf_fuse`, `hybrid_search` |
| `backend/src/rag/schemas/mcp.py` | **Modifier** | `DebugTrace`, champ `debug` sur `SearchHit` |
| `backend/src/rag/schemas/admin.py` | **Modifier** | `HybridConfigSpec`, `HybridConfigResponse` |
| `backend/src/rag/services/mcp.py` | **Modifier** | `_load_hybrid_config`, wire dans `_search_one` |
| `backend/src/rag/api/admin/__init__.py` | **Modifier** | `GET/PUT /workspaces/{name}/hybrid-config` |
| `backend/tests/unit/db/test_hybrid_search.py` | **Créer** | Tests `rrf_fuse`, `lexical_search`, `hybrid_search` |
| `backend/tests/unit/services/test_mcp_hybrid.py` | **Créer** | Tests `_load_hybrid_config` + wire dans `_search_one` |
| `backend/tests/unit/db/test_workspace_search.py` | **Vérifier** | Aucune régression (6 tests existants) |
| `backend/tests/unit/services/test_mcp_search.py` | **Vérifier** | Aucune régression (5 tests existants) |

---

## Task 1 : Migration config 048 — table `hybrid_configs`

**Files:**
- Create: `backend/migrations/048_hybrid_configs.sql`

**Interfaces:**
- Produit: table `hybrid_configs` utilisée par `_load_hybrid_config` (Task 5)

- [ ] **Step 1: Créer la migration SQL**

```sql
-- Migration 048 — hybrid_configs : config recherche hybride par workspace (opt-in)
--
-- Workspace SANS row dans cette table → recherche vectorielle pure (comportement par défaut).
-- Cascade ON DELETE : suppression workspace → suppression hybrid_config auto.

CREATE TABLE hybrid_configs (
    workspace_id  UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    rrf_k         INT NOT NULL DEFAULT 60 CHECK (rrf_k > 0),
    fts_config    TEXT NOT NULL DEFAULT 'simple',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- [ ] **Step 2: Vérifier que la migration s'applique sur l'env connecté**

```bash
cd backend && uv run python -m agflow.db.migrations 2>/dev/null || uv run python -m rag.db.migrations
# Attendu : migration 048 appliquée
```

- [ ] **Step 3: Commit**

```bash
git add backend/migrations/048_hybrid_configs.sql
git commit -m "feat(search): migration 048 — table hybrid_configs (opt-in)"
```

---

## Task 2 : Types internes + `rrf_fuse` (fonction pure)

**Files:**
- Modify: `backend/src/rag/db/workspace_search.py` (ajouter les dataclasses + `rrf_fuse`)
- Create: `backend/tests/unit/db/test_hybrid_search.py` (tests `rrf_fuse`)

**Interfaces:**
- Produit:
  - `_ChildHit(path, chunk_index, chunk_hash, section_id, content, score)` — dataclass interne
  - `_FusedHit(identity, path, chunk_index, section_id, content, rrf_score, vector_rank, vector_score, lexical_rank, lexical_score)` — dataclass interne
  - `rrf_fuse(vector_hits: list[_ChildHit], lexical_hits: list[_ChildHit], k: int = 60) -> list[_FusedHit]`

- [ ] **Step 1: Écrire les tests pour `rrf_fuse`**

Créer `backend/tests/unit/db/test_hybrid_search.py` :

```python
from __future__ import annotations

import pytest
from rag.db.workspace_search import _ChildHit, rrf_fuse


def _ch(path: str, idx: int, hash_: str | None = None, sec: int | None = None, score: float = 0.9) -> _ChildHit:
    return _ChildHit(
        path=path, chunk_index=idx, chunk_hash=hash_,
        section_id=sec, content=f"content of {path}:{idx}", score=score,
    )


class TestRrfFuse:
    def test_chunk_only_in_vector_gets_one_contribution(self):
        v = [_ch("a.py", 0, "h1")]
        result = rrf_fuse(v, [], k=60)
        assert len(result) == 1
        r = result[0]
        assert r.vector_rank == 1
        assert r.lexical_rank is None
        assert abs(r.rrf_score - 1 / (60 + 1)) < 1e-9

    def test_chunk_only_in_lexical_gets_one_contribution(self):
        l = [_ch("b.py", 0, "h2")]
        result = rrf_fuse([], l, k=60)
        assert len(result) == 1
        r = result[0]
        assert r.lexical_rank == 1
        assert r.vector_rank is None
        assert abs(r.rrf_score - 1 / (60 + 1)) < 1e-9

    def test_chunk_in_both_bras_cumulates(self):
        # Même identité (path, chunk_hash)
        v = [_ch("c.py", 0, "h3"), _ch("d.py", 1, "h4")]
        l = [_ch("c.py", 0, "h3"), _ch("e.py", 2, "h5")]
        result = rrf_fuse(v, l, k=60)
        shared = next(r for r in result if r.path == "c.py")
        solo_v = next(r for r in result if r.path == "d.py")
        solo_l = next(r for r in result if r.path == "e.py")
        # shared = 1/(61) + 1/(61) > 1/(61) (solo contributions)
        assert shared.rrf_score > solo_v.rrf_score
        assert shared.rrf_score > solo_l.rrf_score
        assert shared.vector_rank == 1
        assert shared.lexical_rank == 1

    def test_result_sorted_by_rrf_score_desc(self):
        # c.py dans les deux → score le plus haut
        v = [_ch("c.py", 0, "h1"), _ch("a.py", 0, "h2")]
        l = [_ch("c.py", 0, "h1"), _ch("b.py", 0, "h3")]
        result = rrf_fuse(v, l)
        assert result[0].path == "c.py"
        scores = [r.rrf_score for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_legacy_identity_uses_chunk_index(self):
        # chunk_hash=None → identité = (path, chunk_index)
        v = [_ch("a.py", 5, None)]
        l = [_ch("a.py", 5, None)]
        result = rrf_fuse(v, l)
        # Reconnu comme même chunk → un seul résultat, deux contributions
        assert len(result) == 1
        assert result[0].vector_rank == 1
        assert result[0].lexical_rank == 1

    def test_legacy_different_chunk_index_two_results(self):
        v = [_ch("a.py", 0, None)]
        l = [_ch("a.py", 1, None)]  # chunk_index différent → identité différente
        result = rrf_fuse(v, l)
        assert len(result) == 2

    def test_empty_inputs_returns_empty(self):
        assert rrf_fuse([], []) == []

    def test_k_parameter_affects_score(self):
        v = [_ch("a.py", 0, "h1")]
        r60 = rrf_fuse(v, [], k=60)[0]
        r10 = rrf_fuse(v, [], k=10)[0]
        # k plus petit → score plus grand
        assert r10.rrf_score > r60.rrf_score
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

```bash
cd backend && uv run pytest tests/unit/db/test_hybrid_search.py -v 2>&1 | head -20
# Attendu : ImportError ou AttributeError sur _ChildHit / rrf_fuse
```

- [ ] **Step 3: Implémenter `_ChildHit`, `_FusedHit`, `rrf_fuse` dans `workspace_search.py`**

Ajouter **après les imports existants**, avant `vector_search` :

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class _ChildHit:
    """Hit brut d'un bras (vectoriel ou lexical), avant dédup section."""
    path: str
    chunk_index: int
    chunk_hash: str | None
    section_id: int | None
    content: str  # contenu parent (sections.content) ou chunk si legacy
    score: float  # cosinus (vectoriel) ou ts_rank (lexical)

    @property
    def identity(self) -> tuple:
        if self.chunk_hash is not None:
            return (self.path, self.chunk_hash)
        return (self.path, self.chunk_index)


@dataclass
class _FusedHit:
    """Résultat de la fusion RRF, avant dédup section et conversion SearchHit."""
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


def rrf_fuse(
    vector_hits: list[_ChildHit],
    lexical_hits: list[_ChildHit],
    k: int = 60,
) -> list[_FusedHit]:
    """Reciprocal Rank Fusion de deux listes de hits enfants.

    Identité = (path, chunk_hash) si chunk_hash non-null, sinon (path, chunk_index) legacy.
    score_rrf = Σ 1/(k + rang) pour chaque bras où le chunk figure.
    """
    v_rank: dict[tuple, tuple[int, float]] = {
        h.identity: (i + 1, h.score) for i, h in enumerate(vector_hits)
    }
    l_rank: dict[tuple, tuple[int, float]] = {
        h.identity: (i + 1, h.score) for i, h in enumerate(lexical_hits)
    }

    # Collecter toutes les identités uniques, garder le premier _ChildHit rencontré
    seen: dict[tuple, _ChildHit] = {}
    for h in vector_hits:
        seen.setdefault(h.identity, h)
    for h in lexical_hits:
        seen.setdefault(h.identity, h)

    results: list[_FusedHit] = []
    for identity, hit in seen.items():
        vr_vs = v_rank.get(identity)
        lr_ls = l_rank.get(identity)
        rrf = 0.0
        if vr_vs is not None:
            rrf += 1.0 / (k + vr_vs[0])
        if lr_ls is not None:
            rrf += 1.0 / (k + lr_ls[0])
        results.append(
            _FusedHit(
                identity=identity,
                path=hit.path,
                chunk_index=hit.chunk_index,
                section_id=hit.section_id,
                content=hit.content,
                rrf_score=rrf,
                vector_rank=vr_vs[0] if vr_vs else None,
                vector_score=vr_vs[1] if vr_vs else None,
                lexical_rank=lr_ls[0] if lr_ls else None,
                lexical_score=lr_ls[1] if lr_ls else None,
            )
        )
    results.sort(key=lambda h: h.rrf_score, reverse=True)
    return results
```

- [ ] **Step 4: Lancer les tests**

```bash
cd backend && uv run pytest tests/unit/db/test_hybrid_search.py -v
# Attendu : 8 tests PASSED
```

- [ ] **Step 5: Vérifier que les tests existants sont toujours verts**

```bash
cd backend && uv run pytest tests/unit/db/test_workspace_search.py -v
# Attendu : 6 tests PASSED
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/rag/db/workspace_search.py \
        backend/tests/unit/db/test_hybrid_search.py
git commit -m "feat(search): types _ChildHit/_FusedHit + rrf_fuse (fonction pure)"
```

---

## Task 3 : Refactoring `vector_search` + `lexical_search`

**Files:**
- Modify: `backend/src/rag/db/workspace_search.py`
- Modify: `backend/tests/unit/db/test_hybrid_search.py` (ajouter tests lexical)
- Verify: `backend/tests/unit/db/test_workspace_search.py` (aucune régression)

**Interfaces:**
- Consomme: `_ChildHit` (Task 2)
- Produit:
  - `_fetch_vector_children(pool, query_vec, top_k_fetch, min_score) -> list[_ChildHit]` — interne
  - `vector_search(...)` — **signature inchangée**, comportement identique
  - `lexical_search(pool, query, top_k_fetch, fts_config="simple") -> list[_ChildHit]`

- [ ] **Step 1: Écrire les tests `lexical_search`**

Ajouter dans `test_hybrid_search.py` :

```python
from unittest.mock import AsyncMock, MagicMock
from rag.db.workspace_search import lexical_search


def _make_pool_lex(rows: list[dict]) -> MagicMock:
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


class TestLexicalSearch:
    @pytest.mark.asyncio
    async def test_returns_child_hits_ordered_by_ts_rank(self):
        rows = [
            {"path": "a.py", "chunk_index": 0, "chunk_hash": "h1",
             "section_id": None, "content": "hello world", "lexical_score": 0.8},
            {"path": "b.py", "chunk_index": 1, "chunk_hash": "h2",
             "section_id": 5, "content": "parent text", "lexical_score": 0.5},
        ]
        pool = _make_pool_lex(rows)
        hits = await lexical_search(pool, query="hello", top_k_fetch=10)
        assert len(hits) == 2
        assert hits[0].path == "a.py"
        assert hits[0].score == 0.8
        assert hits[0].chunk_hash == "h1"
        assert hits[0].section_id is None
        assert hits[1].section_id == 5

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_list(self):
        pool = _make_pool_lex([])
        hits = await lexical_search(pool, query="notfound", top_k_fetch=5)
        assert hits == []

    @pytest.mark.asyncio
    async def test_passes_top_k_fetch_as_limit(self):
        pool = _make_pool_lex([])
        await lexical_search(pool, query="x", top_k_fetch=42)
        conn = pool.acquire.return_value.__aenter__.return_value
        args = conn.fetch.call_args[0]
        # Dernier arg = LIMIT
        assert args[-1] == 42
```

- [ ] **Step 2: Lancer pour vérifier l'échec**

```bash
cd backend && uv run pytest tests/unit/db/test_hybrid_search.py::TestLexicalSearch -v
# Attendu : ImportError sur lexical_search
```

- [ ] **Step 3: Extraire `_fetch_vector_children` et refactoriser `vector_search`**

Remplacer la fonction `vector_search` dans `workspace_search.py` :

```python
async def _fetch_vector_children(
    workspace_pool: asyncpg.Pool,
    *,
    query_vec: list[float],
    top_k_fetch: int,
    min_score: float,
) -> list[_ChildHit]:
    """Récupère les hits vectoriels bruts (sans dédup section)."""
    async with workspace_pool.acquire() as conn:
        await register_vector(conn)
        await conn.execute("SET ivfflat.probes = 10")
        rows = await conn.fetch(
            """
            SELECT e.path AS path,
                   e.chunk_index AS chunk_index,
                   e.chunk_hash AS chunk_hash,
                   e.section_id AS section_id,
                   COALESCE(s.content, e.content) AS content,
                   1 - (e.embedding <=> $1::vector) AS score
            FROM embeddings e
            LEFT JOIN sections s ON s.id = e.section_id
            ORDER BY e.embedding <=> $1::vector
            LIMIT $2
            """,
            query_vec,
            top_k_fetch,
        )
    return [
        _ChildHit(
            path=r["path"],
            chunk_index=r["chunk_index"],
            chunk_hash=r["chunk_hash"],
            section_id=r["section_id"],
            content=r["content"],
            score=float(r["score"]),
        )
        for r in rows
        if float(r["score"]) >= min_score
    ]


async def vector_search(
    workspace_pool: asyncpg.Pool,
    *,
    query_vec: list[float],
    top_k: int,
    min_score: float,
    workspace_name: str,
    indexer_used: str,
) -> list[SearchHit]:
    """Top-k résultats pgvector avec score cosine >= min_score.

    Small-to-big auto-adaptatif : cherche sur les enfants mais renvoie le
    PARENT (sections.content) quand disponible, dédupliqué par section.
    """
    children = await _fetch_vector_children(
        workspace_pool,
        query_vec=query_vec,
        top_k_fetch=top_k * 4,
        min_score=min_score,
    )
    hits: list[SearchHit] = []
    seen_sections: set[int] = set()
    for child in children:
        if child.section_id is not None:
            if child.section_id in seen_sections:
                continue
            seen_sections.add(child.section_id)
        hits.append(
            SearchHit(
                workspace=workspace_name,
                indexer=indexer_used,
                path=child.path,
                chunk_index=child.chunk_index,
                content=child.content,
                score=child.score,
            )
        )
        if len(hits) >= top_k:
            break
    return hits
```

- [ ] **Step 4: Implémenter `lexical_search`**

Ajouter après `vector_search` :

```python
async def lexical_search(
    workspace_pool: asyncpg.Pool,
    *,
    query: str,
    top_k_fetch: int,
    fts_config: str = "simple",
) -> list[_ChildHit]:
    """Recherche FTS via content_tsv (websearch_to_tsquery, sans stemming).

    Pas de filtre min_score : la correspondance est déjà filtrée par `@@`.
    Pas de dédup section : fait par hybrid_search après RRF.
    """
    async with workspace_pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT e.path AS path,
                   e.chunk_index AS chunk_index,
                   e.chunk_hash AS chunk_hash,
                   e.section_id AS section_id,
                   COALESCE(s.content, e.content) AS content,
                   ts_rank(e.content_tsv, websearch_to_tsquery($2, $1)) AS lexical_score
            FROM embeddings e
            LEFT JOIN sections s ON s.id = e.section_id
            WHERE e.content_tsv @@ websearch_to_tsquery($2, $1)
            ORDER BY lexical_score DESC
            LIMIT $3
            """,
            query,
            fts_config,
            top_k_fetch,
        )
    return [
        _ChildHit(
            path=r["path"],
            chunk_index=r["chunk_index"],
            chunk_hash=r["chunk_hash"],
            section_id=r["section_id"],
            content=r["content"],
            score=float(r["lexical_score"]),
        )
        for r in rows
    ]
```

- [ ] **Step 5: Lancer les tests**

```bash
cd backend && uv run pytest tests/unit/db/test_hybrid_search.py -v
cd backend && uv run pytest tests/unit/db/test_workspace_search.py -v
# Attendu : tous verts (pas de régression vector_search)
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/rag/db/workspace_search.py \
        backend/tests/unit/db/test_hybrid_search.py
git commit -m "feat(search): _fetch_vector_children + lexical_search (FTS websearch_to_tsquery)"
```

---

## Task 4 : `DebugTrace` + champ `debug` sur `SearchHit`

**Files:**
- Modify: `backend/src/rag/schemas/mcp.py`

**Interfaces:**
- Produit:
  - `DebugTrace(vector_rank, vector_score, lexical_rank, lexical_score, rrf_score, rerank_score, final_rank)` — tous `int | None` ou `float | None`
  - `SearchHit.debug: DebugTrace | None = None` (champ additionnel, rétrocompatible)

- [ ] **Step 1: Modifier `schemas/mcp.py`**

```python
class DebugTrace(BaseModel):
    """Trace de debug d'un hit hybride. Peuplée seulement si debug=True."""
    vector_rank: int | None = None
    vector_score: float | None = None
    lexical_rank: int | None = None
    lexical_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None   # null jusqu'à M18 (reranker ne renvoie pas de score)
    final_rank: int | None = None


class SearchHit(BaseModel):
    workspace: str
    indexer: str
    path: str
    chunk_index: int
    content: str
    score: float
    debug: DebugTrace | None = None
```

- [ ] **Step 2: Vérifier que les tests MCP existants sont toujours verts**

```bash
cd backend && uv run pytest tests/unit/services/test_mcp_search.py -v
# Attendu : 5 tests PASSED (debug=None par défaut → rétrocompatible)
```

- [ ] **Step 3: Commit**

```bash
git add backend/src/rag/schemas/mcp.py
git commit -m "feat(search): DebugTrace + champ debug optionnel sur SearchHit"
```

---

## Task 5 : `hybrid_search` — orchestration complète

**Files:**
- Modify: `backend/src/rag/db/workspace_search.py`
- Modify: `backend/tests/unit/db/test_hybrid_search.py`

**Interfaces:**
- Consomme: `_fetch_vector_children`, `lexical_search`, `rrf_fuse`, `SearchHit`, `DebugTrace` (Tasks 2, 3, 4)
- Produit: `hybrid_search(pool, query_vec, query, top_k, min_score, workspace_name, indexer_used, rrf_k=60, fts_config="simple", debug=False) -> list[SearchHit]`

- [ ] **Step 1: Écrire les tests `hybrid_search`**

Ajouter dans `test_hybrid_search.py` :

```python
from unittest.mock import AsyncMock, MagicMock, patch
from rag.db.workspace_search import hybrid_search


def _make_dual_pool(vector_rows: list[dict], lexical_rows: list[dict]) -> MagicMock:
    """Pool qui retourne vector_rows au premier fetch, lexical_rows au second."""
    call_count = 0

    async def _fetch(_query: str, *args):
        nonlocal call_count
        call_count += 1
        # Premier appel = bras vectoriel (_fetch_vector_children)
        # Deuxième appel = lexical_search
        return vector_rows if call_count == 1 else lexical_rows

    conn = MagicMock()
    conn.fetch = AsyncMock(side_effect=_fetch)
    conn.execute = AsyncMock(return_value="SET")

    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


class TestHybridSearch:
    @pytest.mark.asyncio
    async def test_chunk_in_both_bras_ranked_first(self, monkeypatch):
        """Un chunk présent dans les deux bras doit remonter en tête via RRF."""
        shared = {"path": "shared.py", "chunk_index": 0, "chunk_hash": "h_shared",
                  "section_id": None, "content": "shared content", "score": 0.7, "lexical_score": 0.6}
        only_v = {"path": "only_v.py", "chunk_index": 0, "chunk_hash": "h_v",
                  "section_id": None, "content": "vector only", "score": 0.95, "lexical_score": 0.0}

        monkeypatch.setattr("rag.db.workspace_search.register_vector", AsyncMock())
        pool = _make_dual_pool(
            vector_rows=[{**shared, "score": 0.7}, {**only_v, "score": 0.95}],
            lexical_rows=[{**shared, "lexical_score": 0.6}],
        )

        from rag.db import workspace_search as ws_mod
        # Patch pour que les deux fetch() retournent les bonnes colonnes
        # On mock _fetch_vector_children et lexical_search directement
        async def fake_vec(p, *, query_vec, top_k_fetch, min_score):
            from rag.db.workspace_search import _ChildHit
            return [
                _ChildHit("shared.py", 0, "h_shared", None, "shared content", 0.7),
                _ChildHit("only_v.py", 0, "h_v", None, "vector only", 0.95),
            ]

        async def fake_lex(p, *, query, top_k_fetch, fts_config="simple"):
            from rag.db.workspace_search import _ChildHit
            return [
                _ChildHit("shared.py", 0, "h_shared", None, "shared content", 0.6),
            ]

        monkeypatch.setattr(ws_mod, "_fetch_vector_children", fake_vec)
        monkeypatch.setattr(ws_mod, "lexical_search", fake_lex)

        hits = await hybrid_search(
            pool, query_vec=[0.1], query="shared", top_k=5,
            min_score=0.0, workspace_name="ws", indexer_used="openai/m",
        )
        assert hits[0].path == "shared.py"

    @pytest.mark.asyncio
    async def test_section_dedup_after_rrf(self, monkeypatch):
        """Deux enfants d'une même section → un seul hit, meilleur rrf_score."""
        from rag.db import workspace_search as ws_mod
        from rag.db.workspace_search import _ChildHit

        async def fake_vec(p, **kw):
            return [
                _ChildHit("f.py", 0, "h1", section_id=10, content="parent A", score=0.9),
                _ChildHit("f.py", 1, "h2", section_id=10, content="parent A", score=0.8),
            ]

        async def fake_lex(p, **kw):
            return []

        monkeypatch.setattr(ws_mod, "_fetch_vector_children", fake_vec)
        monkeypatch.setattr(ws_mod, "lexical_search", fake_lex)
        monkeypatch.setattr(ws_mod, "register_vector", AsyncMock())

        pool = MagicMock()
        hits = await hybrid_search(
            pool, query_vec=[0.1], query="x", top_k=10,
            min_score=0.0, workspace_name="ws", indexer_used="openai/m",
        )
        assert len(hits) == 1  # section dédupliquée

    @pytest.mark.asyncio
    async def test_debug_false_returns_no_trace(self, monkeypatch):
        from rag.db import workspace_search as ws_mod
        from rag.db.workspace_search import _ChildHit

        async def fake_vec(p, **kw):
            return [_ChildHit("a.py", 0, "h1", None, "c", 0.9)]

        async def fake_lex(p, **kw):
            return []

        monkeypatch.setattr(ws_mod, "_fetch_vector_children", fake_vec)
        monkeypatch.setattr(ws_mod, "lexical_search", fake_lex)

        pool = MagicMock()
        hits = await hybrid_search(
            pool, query_vec=[0.1], query="x", top_k=5,
            min_score=0.0, workspace_name="ws", indexer_used="openai/m",
            debug=False,
        )
        assert all(h.debug is None for h in hits)

    @pytest.mark.asyncio
    async def test_debug_true_populates_trace(self, monkeypatch):
        from rag.db import workspace_search as ws_mod
        from rag.db.workspace_search import _ChildHit

        async def fake_vec(p, **kw):
            return [_ChildHit("a.py", 0, "h1", None, "c", 0.9)]

        async def fake_lex(p, **kw):
            return [_ChildHit("a.py", 0, "h1", None, "c", 0.7)]

        monkeypatch.setattr(ws_mod, "_fetch_vector_children", fake_vec)
        monkeypatch.setattr(ws_mod, "lexical_search", fake_lex)

        pool = MagicMock()
        hits = await hybrid_search(
            pool, query_vec=[0.1], query="x", top_k=5,
            min_score=0.0, workspace_name="ws", indexer_used="openai/m",
            debug=True,
        )
        assert len(hits) == 1
        d = hits[0].debug
        assert d is not None
        assert d.vector_rank == 1
        assert d.lexical_rank == 1
        assert d.rrf_score is not None
        assert d.final_rank == 1
```

- [ ] **Step 2: Lancer pour vérifier l'échec**

```bash
cd backend && uv run pytest tests/unit/db/test_hybrid_search.py::TestHybridSearch -v
# Attendu : ImportError sur hybrid_search
```

- [ ] **Step 3: Implémenter `hybrid_search`**

Ajouter dans `workspace_search.py` après `lexical_search` :

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
) -> list[SearchHit]:
    """Recherche hybride : vectorielle + lexicale, fusionnées par RRF.

    min_score filtre le bras vectoriel uniquement.
    Dédup small-to-big (section_id) après fusion RRF.
    debug=True : chaque SearchHit porte une DebugTrace.
    """
    top_k_fetch = top_k * 4

    vector_children, lexical_children = await asyncio.gather(
        _fetch_vector_children(
            workspace_pool,
            query_vec=query_vec,
            top_k_fetch=top_k_fetch,
            min_score=min_score,
        ),
        lexical_search(
            workspace_pool,
            query=query,
            top_k_fetch=top_k_fetch,
            fts_config=fts_config,
        ),
    )

    fused = rrf_fuse(vector_children, lexical_children, k=rrf_k)

    # Dédup small-to-big par section_id (meilleur rrf_score conservé)
    hits: list[SearchHit] = []
    seen_sections: set[int] = set()
    for rank, fh in enumerate(fused, start=1):
        if fh.section_id is not None:
            if fh.section_id in seen_sections:
                continue
            seen_sections.add(fh.section_id)

        dbg: DebugTrace | None = None
        if debug:
            from rag.schemas.mcp import DebugTrace as _DebugTrace
            dbg = _DebugTrace(
                vector_rank=fh.vector_rank,
                vector_score=fh.vector_score,
                lexical_rank=fh.lexical_rank,
                lexical_score=fh.lexical_score,
                rrf_score=fh.rrf_score,
                final_rank=rank,
            )

        hits.append(
            SearchHit(
                workspace=workspace_name,
                indexer=indexer_used,
                path=fh.path,
                chunk_index=fh.chunk_index,
                content=fh.content,
                score=fh.rrf_score,
                debug=dbg,
            )
        )
        if len(hits) >= top_k:
            break

    return hits
```

Ajouter `import asyncio` en tête si absent (déjà importé via `asyncio.gather` si présent).

- [ ] **Step 4: Lancer tous les tests unitaires DB**

```bash
cd backend && uv run pytest tests/unit/db/ -v
# Attendu : tous verts
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/rag/db/workspace_search.py \
        backend/tests/unit/db/test_hybrid_search.py
git commit -m "feat(search): hybrid_search (RRF + section dédup + debug trace optionnelle)"
```

---

## Task 6 : `_load_hybrid_config` + wire dans `_search_one`

**Files:**
- Modify: `backend/src/rag/services/mcp.py`
- Create: `backend/tests/unit/services/test_mcp_hybrid.py`

**Interfaces:**
- Consomme: `hybrid_search` (Task 5)
- Produit:
  - `_load_hybrid_config(config_pool, workspace_id) -> dict | None`
    - `dict` = `{enabled: bool, rrf_k: int, fts_config: str}`
    - `None` si pas de row dans `hybrid_configs`
  - `_search_one` utilise `hybrid_search` si `hybrid_cfg and hybrid_cfg["enabled"]`, sinon `vector_search`

- [ ] **Step 1: Écrire les tests**

Créer `backend/tests/unit/services/test_mcp_hybrid.py` :

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.schemas.mcp import SearchHit
from rag.services.mcp import McpWorkspaceRef, search


class TestLoadHybridConfig:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_row(self):
        from rag.services.mcp import _load_hybrid_config
        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value=None)
        result = await _load_hybrid_config(pool, uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_dict_when_row_exists(self):
        from rag.services.mcp import _load_hybrid_config
        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value={
            "enabled": True, "rrf_k": 60, "fts_config": "simple"
        })
        result = await _load_hybrid_config(pool, uuid4())
        assert result == {"enabled": True, "rrf_k": 60, "fts_config": "simple"}


class TestSearchOneHybridDispatch:
    """_search_one appelle hybrid_search si hybrid_cfg enabled, vector_search sinon."""

    def _build_pool(self, ws_id, api_key: str, name: str) -> MagicMock:
        from typing import Any
        auth_row = {
            "id": ws_id,
            "api_key_ref": f"${{vault://rag:{name}_apikey}}",
            "indexer_used": "openai/text-embedding-3-small",
        }
        ctx_row = {
            "workspace_name": name, "rag_cnx": "dsn",
            "provider": "openai", "model": "text-embedding-3-small",
            "api_key_ref": None, "base_url": None, "service": "openai",
            "rerank_provider": None, "rerank_model": None,
            "rerank_api_key_ref": None, "rerank_base_url": None,
            "rerank_top_k_pre_rerank": None,
        }
        call_count = 0
        async def _fetchrow(_query: str, *args: Any):
            nonlocal call_count
            call_count += 1
            return auth_row if call_count == 1 else ctx_row
        pool = MagicMock()
        pool.fetchrow = AsyncMock(side_effect=_fetchrow)
        pool.fetchval = AsyncMock(return_value=None)
        return pool

    @pytest.mark.asyncio
    async def test_uses_vector_search_when_no_hybrid_config(self, monkeypatch):
        from rag.services import mcp
        from rag.auth.workspace_auth import ApiKeyCache

        ws_id = uuid4()
        pool = self._build_pool(ws_id, "k", "ws")
        ws_pool = MagicMock()
        registry = MagicMock()
        registry.get_workspace_pool = AsyncMock(return_value=ws_pool)

        fake_vector = AsyncMock(return_value=[
            SearchHit(workspace="ws", indexer="openai/m", path="a.py",
                      chunk_index=0, content="x", score=0.9)
        ])
        fake_hybrid = AsyncMock(return_value=[])
        monkeypatch.setattr(mcp, "vector_search", fake_vector)
        monkeypatch.setattr(mcp, "hybrid_search", fake_hybrid)
        monkeypatch.setattr(mcp, "_load_hybrid_config", AsyncMock(return_value=None))

        provider = MagicMock()
        provider.embed_query = AsyncMock(return_value=[0.1])
        cache = ApiKeyCache()

        hits = await search(
            refs=[McpWorkspaceRef(name="ws", api_key="k")],
            query="x", top_k=5, min_score=0.3,
            config_pool=pool, pool_registry=registry,
            apikey_cache=cache,
            secret_resolver=MagicMock(**{"resolve_with_retry": AsyncMock(return_value="k")}),
            provider_factory=lambda **_: provider,
        )
        fake_vector.assert_awaited_once()
        fake_hybrid.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_uses_hybrid_search_when_enabled(self, monkeypatch):
        from rag.services import mcp
        from rag.auth.workspace_auth import ApiKeyCache

        ws_id = uuid4()
        pool = self._build_pool(ws_id, "k", "ws")
        ws_pool = MagicMock()
        registry = MagicMock()
        registry.get_workspace_pool = AsyncMock(return_value=ws_pool)

        fake_vector = AsyncMock(return_value=[])
        fake_hybrid = AsyncMock(return_value=[
            SearchHit(workspace="ws", indexer="openai/m", path="a.py",
                      chunk_index=0, content="x", score=0.9)
        ])
        monkeypatch.setattr(mcp, "vector_search", fake_vector)
        monkeypatch.setattr(mcp, "hybrid_search", fake_hybrid)
        monkeypatch.setattr(mcp, "_load_hybrid_config",
                            AsyncMock(return_value={"enabled": True, "rrf_k": 60, "fts_config": "simple"}))

        provider = MagicMock()
        provider.embed_query = AsyncMock(return_value=[0.1])
        cache = ApiKeyCache()

        hits = await search(
            refs=[McpWorkspaceRef(name="ws", api_key="k")],
            query="x", top_k=5, min_score=0.3,
            config_pool=pool, pool_registry=registry,
            apikey_cache=cache,
            secret_resolver=MagicMock(**{"resolve_with_retry": AsyncMock(return_value="k")}),
            provider_factory=lambda **_: provider,
        )
        fake_hybrid.assert_awaited_once()
        fake_vector.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_uses_vector_search_when_hybrid_disabled(self, monkeypatch):
        from rag.services import mcp
        from rag.auth.workspace_auth import ApiKeyCache

        ws_id = uuid4()
        pool = self._build_pool(ws_id, "k", "ws")
        ws_pool = MagicMock()
        registry = MagicMock()
        registry.get_workspace_pool = AsyncMock(return_value=ws_pool)

        fake_vector = AsyncMock(return_value=[])
        fake_hybrid = AsyncMock(return_value=[])
        monkeypatch.setattr(mcp, "vector_search", fake_vector)
        monkeypatch.setattr(mcp, "hybrid_search", fake_hybrid)
        monkeypatch.setattr(mcp, "_load_hybrid_config",
                            AsyncMock(return_value={"enabled": False, "rrf_k": 60, "fts_config": "simple"}))

        provider = MagicMock()
        provider.embed_query = AsyncMock(return_value=[0.1])
        cache = ApiKeyCache()

        await search(
            refs=[McpWorkspaceRef(name="ws", api_key="k")],
            query="x", top_k=5, min_score=0.3,
            config_pool=pool, pool_registry=registry,
            apikey_cache=cache,
            secret_resolver=MagicMock(**{"resolve_with_retry": AsyncMock(return_value="k")}),
            provider_factory=lambda **_: provider,
        )
        fake_vector.assert_awaited_once()
        fake_hybrid.assert_not_awaited()
```

- [ ] **Step 2: Lancer pour vérifier l'échec**

```bash
cd backend && uv run pytest tests/unit/services/test_mcp_hybrid.py -v
# Attendu : ImportError ou AttributeError sur _load_hybrid_config / hybrid_search
```

- [ ] **Step 3: Implémenter `_load_hybrid_config` dans `services/mcp.py`**

Ajouter après `_load_workspace_context` :

```python
async def _load_hybrid_config(
    config_pool: asyncpg.Pool,
    workspace_id: object,
) -> dict[str, object] | None:
    """Charge la config hybride d'un workspace depuis hybrid_configs.

    Retourne None si pas de row (pas de comportement hybride).
    """
    row = await config_pool.fetchrow(
        "SELECT enabled, rrf_k, fts_config FROM hybrid_configs WHERE workspace_id = $1",
        workspace_id,
    )
    if row is None:
        return None
    return {"enabled": row["enabled"], "rrf_k": row["rrf_k"], "fts_config": row["fts_config"]}
```

- [ ] **Step 4: Modifier `_search_one` pour dispatcher vector vs hybrid**

Dans les imports de `services/mcp.py`, ajouter :
```python
from rag.db.workspace_search import hybrid_search, vector_search
```
(Remplacer l'import existant `from rag.db.workspace_search import vector_search`)

Modifier dans `_search_one` la partie qui appelle `vector_search` :

```python
    # Charger config hybride (None = vectoriel pur)
    hybrid_cfg = await _load_hybrid_config(config_pool, auth.workspace_id)

    ws_pool = await pool_registry.get_workspace_pool(ref.name, ctx["rag_cnx"])

    if hybrid_cfg and hybrid_cfg["enabled"]:
        hits = await hybrid_search(
            ws_pool,
            query_vec=query_vec,
            query=query,
            top_k=pre_top_k,
            min_score=min_score,
            workspace_name=ref.name,
            indexer_used=auth.indexer_used,
            rrf_k=int(hybrid_cfg["rrf_k"]),
            fts_config=str(hybrid_cfg["fts_config"]),
            debug=False,  # jamais de trace dans le flux agent MCP
        )
    else:
        hits = await vector_search(
            ws_pool,
            query_vec=query_vec,
            top_k=pre_top_k,
            min_score=min_score,
            workspace_name=ref.name,
            indexer_used=auth.indexer_used,
        )
```

Le paramètre `query` doit être ajouté à `_search_one` (il vient de `search()` qui a déjà `query`).

- [ ] **Step 5: Lancer tous les tests services**

```bash
cd backend && uv run pytest tests/unit/services/ -v
# Attendu : tous verts (test_mcp_search.py non-régressé + test_mcp_hybrid.py vert)
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/rag/services/mcp.py \
        backend/tests/unit/services/test_mcp_hybrid.py
git commit -m "feat(search): _load_hybrid_config + dispatch hybrid/vector dans _search_one"
```

---

## Task 7 : Schémas admin + endpoints `GET/PUT /workspaces/{name}/hybrid-config`

**Files:**
- Modify: `backend/src/rag/schemas/admin.py`
- Modify: `backend/src/rag/api/admin/__init__.py`

**Interfaces:**
- Consomme: table `hybrid_configs` (Task 1)
- Produit:
  - `GET /workspaces/{name}/hybrid-config` → `HybridConfigResponse` | 404
  - `PUT /workspaces/{name}/hybrid-config` payload `HybridConfigSpec` → `HybridConfigResponse` (upsert)

- [ ] **Step 1: Ajouter les schémas dans `schemas/admin.py`**

```python
class HybridConfigSpec(BaseModel):
    """Body PUT /workspaces/{name}/hybrid-config."""
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    rrf_k: int = Field(default=60, gt=0, le=1000)
    fts_config: str = Field(default="simple", min_length=1, max_length=63)


class HybridConfigResponse(BaseModel):
    """Réponse GET / PUT /workspaces/{name}/hybrid-config."""
    workspace_id: UUID
    enabled: bool
    rrf_k: int
    fts_config: str
    created_at: str
    updated_at: str
```

Ajouter l'import `UUID` si absent.

- [ ] **Step 2: Ajouter les endpoints dans `api/admin/__init__.py`**

Ajouter dans les imports de schémas :
```python
from rag.schemas.admin import (
    ...
    HybridConfigResponse,
    HybridConfigSpec,
    ...
)
```

Ajouter dans `build_admin_router()` après la section `# ─── Rerank configs` :

```python
    # ─── Hybrid configs ─────────────────────────────────────────────────────

    @router.get("/workspaces/{name}/hybrid-config")
    async def get_hybrid_config_endpoint(
        name: str, request: Request
    ) -> HybridConfigResponse:
        """Config recherche hybride du workspace.

        404 workspace_not_found si workspace inconnu.
        404 hybrid_not_configured si pas de row dans hybrid_configs.
        """
        pool = _config_pool(request)
        ws_row = await pool.fetchrow("SELECT id FROM workspaces WHERE name = $1", name)
        if ws_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="workspace_not_found")
        cfg = await pool.fetchrow(
            "SELECT workspace_id, enabled, rrf_k, fts_config, created_at, updated_at "
            "FROM hybrid_configs WHERE workspace_id = $1",
            ws_row["id"],
        )
        if cfg is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="hybrid_not_configured")
        return HybridConfigResponse(
            workspace_id=cfg["workspace_id"],
            enabled=cfg["enabled"],
            rrf_k=cfg["rrf_k"],
            fts_config=cfg["fts_config"],
            created_at=cfg["created_at"].isoformat(),
            updated_at=cfg["updated_at"].isoformat(),
        )

    @router.put("/workspaces/{name}/hybrid-config")
    async def put_hybrid_config_endpoint(
        name: str, payload: HybridConfigSpec, request: Request
    ) -> HybridConfigResponse:
        """Upsert la config hybride (INSERT ON CONFLICT DO UPDATE).

        404 si workspace inconnu. Retourne la config après upsert.
        """
        pool = _config_pool(request)
        ws_row = await pool.fetchrow("SELECT id FROM workspaces WHERE name = $1", name)
        if ws_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="workspace_not_found")
        cfg = await pool.fetchrow(
            """
            INSERT INTO hybrid_configs (workspace_id, enabled, rrf_k, fts_config)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (workspace_id) DO UPDATE
            SET enabled    = EXCLUDED.enabled,
                rrf_k      = EXCLUDED.rrf_k,
                fts_config = EXCLUDED.fts_config,
                updated_at = now()
            RETURNING workspace_id, enabled, rrf_k, fts_config, created_at, updated_at
            """,
            ws_row["id"],
            payload.enabled,
            payload.rrf_k,
            payload.fts_config,
        )
        return HybridConfigResponse(
            workspace_id=cfg["workspace_id"],
            enabled=cfg["enabled"],
            rrf_k=cfg["rrf_k"],
            fts_config=cfg["fts_config"],
            created_at=cfg["created_at"].isoformat(),
            updated_at=cfg["updated_at"].isoformat(),
        )
```

- [ ] **Step 3: Lancer lint**

```bash
cd backend && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
# Attendu : aucune erreur
```

- [ ] **Step 4: Lancer tous les tests**

```bash
cd backend && uv run pytest tests/unit/ -v
# Attendu : tous verts
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/rag/schemas/admin.py \
        backend/src/rag/api/admin/__init__.py
git commit -m "feat(search): endpoints GET/PUT /workspaces/{name}/hybrid-config"
```

---

## Task 8 : Vérification finale — non-régression + lint

**Files:**
- Verify: tous les fichiers modifiés

- [ ] **Step 1: Lancer la suite complète**

```bash
cd backend && uv run pytest tests/ -v --tb=short 2>&1 | tail -30
# Attendu : 0 failures
```

- [ ] **Step 2: Lint + format**

```bash
cd backend && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
```

- [ ] **Step 3: Vérifier que les 6 tests `test_workspace_search.py` sont intacts**

```bash
cd backend && uv run pytest tests/unit/db/test_workspace_search.py -v
# Attendu : 6 PASSED — aucune régression vector_search
```

- [ ] **Step 4: Vérifier que les 5 tests `test_mcp_search.py` sont intacts**

```bash
cd backend && uv run pytest tests/unit/services/test_mcp_search.py -v
# Attendu : 5 PASSED
```

- [ ] **Step 5: Commit de clôture si tout est vert**

```bash
git add -u
git commit -m "feat(search): M16 recherche hybride vectoriel+lexical+RRF livré"
```

---

## Self-Review

**Spec coverage :**
- ✅ `content_tsv` GENERATED ALWAYS AS + GIN index (Task 1 migration workspace, déjà créée)
- ✅ `hybrid_configs` opt-in (Task 1)
- ✅ `lexical_search` via `websearch_to_tsquery` (Task 3)
- ✅ `rrf_fuse` pure, testée isolément (Task 2)
- ✅ `hybrid_search` = vector + lexical + RRF + section-dédup (Task 5)
- ✅ `min_score` sur bras vectoriel uniquement (Task 3 + 5)
- ✅ Identité `(path, chunk_hash)` / fallback `(path, chunk_index)` legacy (Task 2)
- ✅ `debug=True` → `DebugTrace` peuplée ; `debug=False` → `None` (Tasks 4 + 5)
- ✅ `debug=False` dans le flux MCP agent, jamais de trace en prod (Task 6)
- ✅ Comportement inchangé sans `hybrid_configs` row (Task 6 + tests)
- ✅ `GET/PUT /workspaces/{name}/hybrid-config` (Task 7)
- ⚠️ `rerank_score` dans `DebugTrace` : champ présent mais toujours `null` — le reranker (`_search_one`) ne retourne pas de score par document. Documenté dans le champ Pydantic. À remplir quand l'interface rerank expose les scores.
- ⚠️ Trace debug playground (`playground.py` passe `debug=True`) : hors scope de ce plan — `hybrid_search` supporte déjà `debug=True`, l'intégration playground est M16-bis.
- ⚠️ Multi-workspace hétérogène (hybrides + non-hybrides) : la fusion inter-workspace reste par score, non couverte par ce plan — comportement actuel inchangé.
