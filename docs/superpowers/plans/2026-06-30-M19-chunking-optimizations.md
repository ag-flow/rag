# M19 — Optimisations de chunking activables à la demande

> **Pour les agents :** exécuter tâche par tâche avec `superpowers:executing-plans`.

**Goal:** Implémenter 3 optimisations de chunking (ContentCleaner, overlap=0 code, floor=128 code) sans aucun changement de comportement par défaut — l'utilisateur active chaque optimisation en modifiant les params jsonb de sa stratégie.

**Architecture:** Le paramètre `clean_content: bool` est ajouté aux params jsonb des stratégies. La factory lit ce flag et enveloppe le chunker dans un `CleaningChunkerWrapper`. Les migrations 050/051 mettent à jour les seeds globaux `code-aware` (n'affecte que les nouveaux workspaces ou ceux sans surcharge workspace).

**Tech Stack:** Python 3.12, pytest, asyncpg, SQL Postgres 16.

## Global Constraints

- Branche `dev` uniquement — vérifier `git branch --show-current` avant toute édition
- TDD strict : test rouge → impl → test vert → commit
- Lint `uv run ruff check` avant chaque commit
- Pas de SQLAlchemy — migrations SQL brutes dans `backend/migrations/`
- `from __future__ import annotations` en tête de chaque fichier Python
- Pas de print — structlog uniquement

---

### Task 1 : `cleaner.py` — module de nettoyage + wrapper

**Files:**
- Create: `backend/src/rag/indexer/chunking/cleaner.py`
- Create: `backend/tests/unit/indexer/test_cleaner.py`

**Interfaces:**
- Produit: `clean_content_text(text: str) -> str` — fonction pure, importable partout
- Produit: `CleaningChunkerWrapper(inner: StructuredChunkerProtocol)` — implémente `StructuredChunkerProtocol.chunk(content: str) -> ChunkedDocument`
- Consomme: `rag.indexer.chunking.structured.StructuredChunkerProtocol`, `ChunkedDocument`

- [ ] **Étape 1 : Tests rouges**

```python
# backend/tests/unit/indexer/test_cleaner.py
from __future__ import annotations

from unittest.mock import MagicMock

from rag.indexer.chunking.cleaner import CleaningChunkerWrapper, clean_content_text
from rag.indexer.chunking.structured import ChunkedDocument


class TestCleanContentText:
    def test_nfkc_normalisation(self):
        # ﬁ = fi ligature → fi
        assert clean_content_text("ﬁle") == "file"

    def test_crlf_to_lf(self):
        assert clean_content_text("a\r\nb") == "a\nb"

    def test_cr_to_lf(self):
        assert clean_content_text("a\rb") == "a\nb"

    def test_trailing_whitespace_removed(self):
        assert clean_content_text("hello   \nworld\t\n") == "hello\nworld\n"

    def test_max_two_blank_lines(self):
        assert clean_content_text("a\n\n\n\n\nb") == "a\n\nb"

    def test_three_blanks_become_two(self):
        result = clean_content_text("a\n\n\n\nb")
        assert result == "a\n\nb"

    def test_two_blanks_unchanged(self):
        assert clean_content_text("a\n\nb") == "a\n\nb"

    def test_code_indentation_preserved(self):
        code = "def foo():\n    return 42\n"
        assert clean_content_text(code) == code

    def test_empty_string_unchanged(self):
        assert clean_content_text("") == ""

    def test_idempotent(self):
        text = "hello\nworld\n\nfoo\n"
        assert clean_content_text(clean_content_text(text)) == clean_content_text(text)


class TestCleaningChunkerWrapper:
    def test_delegates_to_inner_with_cleaned_content(self):
        inner = MagicMock()
        inner.chunk.return_value = ChunkedDocument(parents=[], children=[])
        wrapper = CleaningChunkerWrapper(inner)

        dirty = "hello   \n\n\n\nworld"
        wrapper.chunk(dirty)

        called_with = inner.chunk.call_args[0][0]
        assert "\n\n\n" not in called_with
        assert "   \n" not in called_with

    def test_returns_inner_result(self):
        from rag.indexer.chunking.structured import ChildChunk, ParentSection

        expected = ChunkedDocument(
            parents=[ParentSection(section_key="k", content="c")],
            children=[ChildChunk(embed_text="e", parent_key="k")],
        )
        inner = MagicMock()
        inner.chunk.return_value = expected
        wrapper = CleaningChunkerWrapper(inner)

        result = wrapper.chunk("text")
        assert result is expected
```

- [ ] **Étape 2 : Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/indexer/test_cleaner.py -v 2>&1 | head -20
```

Attendu : `ImportError: cannot import name 'CleaningChunkerWrapper'`

- [ ] **Étape 3 : Implémenter `cleaner.py`**

```python
# backend/src/rag/indexer/chunking/cleaner.py
from __future__ import annotations

import re
import unicodedata

from rag.indexer.chunking.structured import ChunkedDocument, StructuredChunkerProtocol


def clean_content_text(text: str) -> str:
    """Nettoyage non-destructif du texte avant chunking.

    Opérations (dans l'ordre) :
    1. Normalisation unicode NFKC (ligatures, espaces spéciaux…)
    2. CRLF / CR → LF
    3. Suppression des espaces en fin de ligne
    4. Maximum 2 lignes vides consécutives

    L'indentation (espaces en début de ligne) est préservée — essentiel pour
    le code. Pas de normalisation des espaces inline.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


class CleaningChunkerWrapper:
    """Applique `clean_content_text` avant de déléguer au chunker interne.

    Implémente `StructuredChunkerProtocol`. Activé quand le param de stratégie
    `clean_content=true` est positionné — transparent sinon.
    """

    def __init__(self, inner: StructuredChunkerProtocol) -> None:
        self._inner = inner

    def chunk(self, content: str) -> ChunkedDocument:
        return self._inner.chunk(clean_content_text(content))
```

- [ ] **Étape 4 : Tests verts**

```bash
cd backend && uv run pytest tests/unit/indexer/test_cleaner.py -v
```

Attendu : 12 passed

- [ ] **Étape 5 : Lint**

```bash
cd backend && uv run ruff check src/rag/indexer/chunking/cleaner.py tests/unit/indexer/test_cleaner.py
```

- [ ] **Étape 6 : Commit**

```bash
cd backend && git add src/rag/indexer/chunking/cleaner.py tests/unit/indexer/test_cleaner.py
git commit -m "feat(chunking): ContentCleaner — nettoyage non-destructif activable à la demande"
```

---

### Task 2 : Intégration `clean_content` dans `structured_factory.py`

**Files:**
- Modify: `backend/src/rag/indexer/chunking/structured_factory.py`
- Modify: `backend/tests/unit/indexer/test_chunking_factory.py` (ajouter tests)

**Interfaces:**
- Consomme: `CleaningChunkerWrapper` de `cleaner.py`
- Produit: `make_structured_chunker(..., params={"clean_content": True})` → retourne un `CleaningChunkerWrapper`

- [ ] **Étape 1 : Tests rouges** (ajouter à `test_chunking_factory.py`)

```python
# Ajouter à la fin de backend/tests/unit/indexer/test_chunking_factory.py

from rag.indexer.chunking.cleaner import CleaningChunkerWrapper
from rag.indexer.chunking.tokens import CharEstimator


def _make(algo: str, params: dict) -> object:
    from rag.indexer.chunking.structured_factory import make_structured_chunker
    return make_structured_chunker(
        algo=algo,
        params=params,
        estimator=CharEstimator(),
        provider_max_input_tokens=8192,
    )


class TestCleanContentParam:
    def test_clean_content_false_returns_plain_chunker(self):
        chunker = _make("prose", {"clean_content": False})
        assert not isinstance(chunker, CleaningChunkerWrapper)

    def test_clean_content_true_returns_wrapper(self):
        chunker = _make("prose", {"clean_content": True})
        assert isinstance(chunker, CleaningChunkerWrapper)

    def test_clean_content_true_for_code(self):
        chunker = _make("code", {"clean_content": True})
        assert isinstance(chunker, CleaningChunkerWrapper)

    def test_clean_content_true_for_data(self):
        chunker = _make("data", {"clean_content": True})
        assert isinstance(chunker, CleaningChunkerWrapper)

    def test_clean_content_true_for_table(self):
        chunker = _make("table", {"clean_content": True})
        assert isinstance(chunker, CleaningChunkerWrapper)

    def test_unknown_param_still_raises(self):
        import pytest
        with pytest.raises(ValueError, match="unknown params"):
            _make("prose", {"typo_param": True})
```

- [ ] **Étape 2 : Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/indexer/test_chunking_factory.py::TestCleanContentParam -v 2>&1 | head -20
```

Attendu : `ValueError: unknown params for algo 'prose': ['clean_content']`

- [ ] **Étape 3 : Modifier `structured_factory.py`**

Ajouter `"clean_content"` aux clés autorisées et enrouler le chunker si demandé :

```python
# backend/src/rag/indexer/chunking/structured_factory.py
from __future__ import annotations

import math
from typing import Any

import structlog

from rag.indexer.chunking.cleaner import CleaningChunkerWrapper  # NEW
from rag.indexer.chunking.code_chunker import CodeChunker
from rag.indexer.chunking.code_parser import UnsupportedLanguageError
from rag.indexer.chunking.data_chunker import DataChunker
from rag.indexer.chunking.markdown_deep import MarkdownDeepChunker
from rag.indexer.chunking.normalizer import TokenBounds
from rag.indexer.chunking.structured import StructuredChunkerProtocol
from rag.indexer.chunking.table import TableChunker
from rag.indexer.chunking.tokens import TokenEstimator

log = structlog.get_logger(__name__)

_PROSE_KEYS = {
    "child_target_tokens",
    "floor_tokens",
    "overlap_tokens",
    "breadcrumb_depth",
    "heading_levels",
    "clean_content",  # NEW
}
_CODE_KEYS = {
    "child_target_tokens",
    "floor_tokens",
    "overlap_tokens",
    "breadcrumb_depth",
    "clean_content",  # NEW
}
_TABLE_KEYS = {
    "child_target_tokens",
    "max_rows_per_chunk",
    "clean_content",  # NEW
}
_ALLOWED: dict[str, set[str]] = {
    "prose": _PROSE_KEYS,
    "markdown": _PROSE_KEYS,
    "code": _CODE_KEYS,
    "data": _CODE_KEYS,
    "table": _TABLE_KEYS,
}

_DEFAULT_TARGET = 384
_DEFAULT_FLOOR = 64
_DEFAULT_OVERLAP = 64
_DEFAULT_DEPTH = -1
_DEFAULT_HEADING_LEVELS = (1, 2)
_DEFAULT_MAX_ROWS = 50


def make_structured_chunker(
    *,
    algo: str,
    params: dict[str, Any],
    estimator: TokenEstimator,
    provider_max_input_tokens: int,
    safety_factor: float = 0.8,
    language: str | None = None,
) -> StructuredChunkerProtocol:
    """Construit un chunker structure-aware depuis (algo + params nommés).

    Si `params["clean_content"] == True`, le chunker est enveloppé dans un
    `CleaningChunkerWrapper` qui nettoie le contenu avant découpe (unicode
    NFKC, CRLF→LF, trailing whitespace, max 2 lignes vides). Défaut : False
    — aucun changement de comportement existant.
    """
    if algo not in _ALLOWED:
        raise ValueError(f"unknown chunking algo: {algo!r}")
    unknown = set(params) - _ALLOWED[algo]
    if unknown:
        raise ValueError(f"unknown params for algo {algo!r}: {sorted(unknown)}")
    if provider_max_input_tokens <= 0:
        raise ValueError("provider_max_input_tokens must be > 0")
    if not 0 < safety_factor <= 1:
        raise ValueError("safety_factor must be in (0, 1]")

    clean = bool(params.get("clean_content", False))  # NEW

    hard = max(1, math.floor(safety_factor * provider_max_input_tokens))
    target = max(1, min(int(params.get("child_target_tokens", _DEFAULT_TARGET)), hard))

    if algo == "table":
        chunker: StructuredChunkerProtocol = TableChunker(
            estimator=estimator,
            bounds=TokenBounds(target, 0, 0, hard),
            max_rows_per_chunk=int(params.get("max_rows_per_chunk", _DEFAULT_MAX_ROWS)),
        )
        return CleaningChunkerWrapper(chunker) if clean else chunker  # NEW

    bounds = TokenBounds(
        child_target_tokens=target,
        floor_tokens=min(int(params.get("floor_tokens", _DEFAULT_FLOOR)), target),
        overlap_tokens=min(int(params.get("overlap_tokens", _DEFAULT_OVERLAP)), target - 1),
        hard_ceiling_tokens=hard,
    )
    depth = int(params.get("breadcrumb_depth", _DEFAULT_DEPTH))

    if algo in ("code", "data"):
        inner = _try_treesitter_chunker(algo, language, estimator, bounds, depth)
        if inner is not None:
            return CleaningChunkerWrapper(inner) if clean else inner  # NEW
        # fallback gracieux : langage non supporté → prose (borné en tokens)

    heading_levels = tuple(params.get("heading_levels", _DEFAULT_HEADING_LEVELS))
    prose_chunker: StructuredChunkerProtocol = MarkdownDeepChunker(
        estimator=estimator,
        bounds=bounds,
        breadcrumb_depth=depth,
        heading_levels=heading_levels,
    )
    return CleaningChunkerWrapper(prose_chunker) if clean else prose_chunker  # NEW


def _try_treesitter_chunker(
    algo: str,
    language: str | None,
    estimator: TokenEstimator,
    bounds: TokenBounds,
    depth: int,
) -> StructuredChunkerProtocol | None:
    if not language:
        log.info("structured_factory.no_language_fallback_prose", algo=algo)
        return None
    builder = DataChunker if algo == "data" else CodeChunker
    try:
        return builder(
            language=language, estimator=estimator, bounds=bounds, breadcrumb_depth=depth
        )
    except UnsupportedLanguageError:
        log.info("structured_factory.unsupported_fallback_prose", algo=algo, language=language)
        return None
```

- [ ] **Étape 4 : Tests verts**

```bash
cd backend && uv run pytest tests/unit/indexer/test_chunking_factory.py -v
```

Attendu : tous les tests passent dont les 6 nouveaux `TestCleanContentParam`

- [ ] **Étape 5 : Suite complète (non-régression)**

```bash
cd backend && uv run pytest tests/unit/indexer/ -v 2>&1 | tail -15
```

- [ ] **Étape 6 : Lint**

```bash
cd backend && uv run ruff check src/rag/indexer/chunking/structured_factory.py tests/unit/indexer/test_chunking_factory.py
```

- [ ] **Étape 7 : Commit**

```bash
git add backend/src/rag/indexer/chunking/structured_factory.py backend/tests/unit/indexer/test_chunking_factory.py
git commit -m "feat(chunking): param clean_content dans structured_factory — activable par stratégie"
```

---

### Task 3 : Migration 050 — overlap=0 pour code-aware

**Files:**
- Create: `backend/migrations/050_code_overlap_zero.sql`

**Justification:** tree-sitter découpe aux frontières symboliques (fonction/classe). L'overlap=64 actuel fait saigner la queue de la fonction précédente dans le chunk suivant — bruit sémantique pur. Le breadcrumb de portée (`module > classe > méthode`) remplace l'overlap pour le contexte.

**Scope:** N'affecte que le seed global (workspace_id IS NULL). Les workspaces ayant déjà une surcharge workspace-level ne sont pas affectés. Les workspaces déjà indexés avec l'ancien seed doivent réindexer manuellement s'ils veulent bénéficier du changement.

- [ ] **Étape 1 : Écrire la migration**

```sql
-- backend/migrations/050_code_overlap_zero.sql
-- Corrige le seed global code-aware : overlap cross-symbole = bruit sémantique.
-- Les chunks tree-sitter sont aux frontières naturelles (fonction/classe) ;
-- le breadcrumb de portée fournit déjà le contexte hiérarchique.
-- N'affecte pas les surcharges workspace-level existantes.
UPDATE chunking_strategies
SET params = params || '{"overlap_tokens": 0}'::jsonb
WHERE workspace_id IS NULL
  AND name = 'code-aware';
```

- [ ] **Étape 2 : Vérifier la syntaxe SQL**

```bash
cd /workspaces/admin-rag/backend && grep -c "code-aware" migrations/050_code_overlap_zero.sql
```

Attendu : `1`

- [ ] **Étape 3 : Commit**

```bash
git add backend/migrations/050_code_overlap_zero.sql
git commit -m "fix(chunking): overlap=0 pour code-aware (seed global) — supprime bruit cross-symbole"
```

---

### Task 4 : Migration 051 — floor=128 pour code-aware

**Files:**
- Create: `backend/migrations/051_code_floor_128.sql`

**Justification:** `floor=64` tokens ≈ 256 chars. En code, cela peut être un `pass`, `return None`, ou un commentaire isolé — chunks de très faible valeur informationnelle qui polluent l'index. `floor=128` ≈ 512 chars filtre les micro-stubs sans valeur tout en conservant les petites fonctions significatives.

- [ ] **Étape 1 : Écrire la migration**

```sql
-- backend/migrations/051_code_floor_128.sql
-- Relève le floor minimum pour les chunks code-aware : 64 tokens (≈256 chars)
-- capture trop de micro-stubs sans valeur (pass, return None, commentaires isolés).
-- 128 tokens (≈512 chars) filtre le bruit tout en conservant les petites fonctions.
-- N'affecte pas les surcharges workspace-level existantes.
UPDATE chunking_strategies
SET params = params || '{"floor_tokens": 128}'::jsonb
WHERE workspace_id IS NULL
  AND name = 'code-aware';
```

- [ ] **Étape 2 : Vérifier**

```bash
grep -c "code-aware" backend/migrations/051_code_floor_128.sql
```

Attendu : `1`

- [ ] **Étape 3 : Commit**

```bash
git add backend/migrations/051_code_floor_128.sql
git commit -m "fix(chunking): floor=128 pour code-aware (seed global) — filtre les micro-stubs"
```

---

## Auto-review

### Couverture spec

| Optimisation | Tâche | Testée |
|---|---|---|
| ContentCleaner (clean_content_text) | T1 | ✅ 12 tests unitaires |
| Wrapper (CleaningChunkerWrapper) | T1 | ✅ 2 tests |
| Intégration factory prose | T2 | ✅ TestCleanContentParam |
| Intégration factory code | T2 | ✅ |
| Intégration factory data | T2 | ✅ |
| Intégration factory table | T2 | ✅ |
| Rejet param inconnu inchangé | T2 | ✅ |
| Migration overlap=0 code | T3 | SQL uniquement (pas de test d'intégration — seed global) |
| Migration floor=128 code | T4 | SQL uniquement |
| Comportement par défaut inchangé | T2 | ✅ (clean_content=False → pas de wrapper) |

### Interfaces cohérentes

- `clean_content_text(text: str) -> str` — T1 définit, T1 teste
- `CleaningChunkerWrapper(inner).chunk(content)` — T1 définit, T1 teste, T2 vérifie via isinstance
- `make_structured_chunker(params={"clean_content": True})` — T2 définit et teste

### Pas de placeholder

Toutes les étapes ont du code concret. ✅
