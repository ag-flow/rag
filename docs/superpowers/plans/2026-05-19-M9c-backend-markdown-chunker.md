# M9c — Backend Markdown Chunker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer la stratégie de chunking sémantique `markdown` : découpe d'un document Markdown en sections H1/H2 (configurable), préserve les fences ` ``` ` intacts, délègue à `ParagraphChunker` pour les sections trop longues, enrichit chaque `Chunk` d'un metadata `{section_title, section_path, heading_level}`.

**Architecture:** Nouveau `MarkdownChunker` dans le package `chunking/` qui parse via `markdown-it-py`, découpe par tokens `heading_open` aux niveaux configurés, compose avec `ParagraphChunker` existant pour les sections > `max_chars`. Pattern factory miroir M9-T3. Aucune modification du schéma DB `embeddings` (la metadata jsonb arrive nativement via M9-T6). Frontend différé (M9c-front ultérieur).

**Tech Stack:** Python 3.12, asyncpg, Pydantic v2, markdown-it-py>=3.0,<4.0, pytest + pytest-asyncio. Pattern de référence : `backend/src/rag/indexer/chunking/paragraph.py` (M9-T3).

**Spec design** : `docs/superpowers/specs/2026-05-19-M9c-backend-markdown-chunker-design.md`

---

## File Structure

| Fichier | Statut | Responsabilité |
|---|---|---|
| `backend/pyproject.toml` | **Modify** | Ajout dépendance `markdown-it-py>=3.0,<4.0` |
| `backend/migrations/014_chunking_strategy_markdown.sql` | **Create** | Élargit `CHECK chunking_configs.strategy IN ('paragraph','markdown')` |
| `backend/src/rag/indexer/chunking/markdown.py` | **Create** | `MarkdownChunker` + helpers privés + dataclass `_Section` |
| `backend/src/rag/indexer/chunking/factory.py` | **Modify** | Branche `if strategy == "markdown"` + helper `_make_markdown_chunker` |
| `backend/src/rag/indexer/chunking/__init__.py` | **Modify** | Export `MarkdownChunker` |
| `backend/src/rag/schemas/admin.py` | **Modify** | `Literal["paragraph","markdown"]` + `_validate_extras` dispatché + `_validate_markdown_extras` helper |
| `backend/tests/integration/test_migration_014_chunking_strategy_markdown.py` | **Create** | 3 tests (accepte markdown, accepte paragraph, rejette inconnu) |
| `backend/tests/unit/indexer/test_chunking_markdown.py` | **Create** | 17 tests (sections, fences, fallback, breadcrumb, malformés) |
| `backend/tests/unit/indexer/test_chunking_factory.py` | **Modify** | +5 tests pour la branche markdown |
| `backend/tests/unit/schemas/test_chunking_config_schema.py` | **Modify** | +7 tests pour les extras markdown |
| `backend/tests/integration/test_real_indexer_markdown.py` | **Create** | 1 test e2e (indexation README via MarkdownChunker) |
| `specs/09-roadmap.md` | **Modify** | Marquer M9c livré |

---

## Task 1 — Dépendance + migration 014 + tests migration

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/migrations/014_chunking_strategy_markdown.sql`
- Create: `backend/tests/integration/test_migration_014_chunking_strategy_markdown.py`

### Step 1 : Vérifier le nom exact de la contrainte CHECK

Lancer (depuis backend/) avec les env vars de test :

```bash
TEST_POSTGRES_HOST=192.168.10.171 TEST_POSTGRES_PORT=5432 TEST_POSTGRES_USER=rag TEST_POSTGRES_PASSWORD=jQSKUdhlLghgQ2slb85WTRN1cBMCqqJe \
  uv run python -c "
import asyncio, asyncpg
async def main():
    conn = await asyncpg.connect('postgresql://rag:jQSKUdhlLghgQ2slb85WTRN1cBMCqqJe@192.168.10.171:5432/postgres')
    rows = await conn.fetch(\"SELECT conname FROM pg_constraint WHERE conrelid = 'chunking_configs'::regclass AND contype='c'\")
    for r in rows: print(r['conname'])
    await conn.close()
asyncio.run(main())
"
```

Expected : `chunking_configs_strategy_check` (pattern Postgres auto). Si autre nom, l'utiliser dans la migration.

### Step 2 : Écrire les tests migration (rouge)

`backend/tests/integration/test_migration_014_chunking_strategy_markdown.py` :

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
async def test_chunking_configs_accepts_markdown_strategy(
    session_pool: asyncpg.Pool,
) -> None:
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_md_strategy")
        await conn.execute(
            "INSERT INTO chunking_configs "
            "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
            "VALUES ($1, 'markdown', 2000, 200, 200)",
            ws_id,
        )
        row = await conn.fetchrow(
            "SELECT strategy FROM chunking_configs WHERE workspace_id = $1", ws_id,
        )
    assert row is not None
    assert row["strategy"] == "markdown"


@pytest.mark.asyncio
async def test_chunking_configs_still_accepts_paragraph(
    session_pool: asyncpg.Pool,
) -> None:
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_md_para")
        await conn.execute(
            "INSERT INTO chunking_configs "
            "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
            "VALUES ($1, 'paragraph', 2000, 200, 200)",
            ws_id,
        )
        row = await conn.fetchrow(
            "SELECT strategy FROM chunking_configs WHERE workspace_id = $1", ws_id,
        )
    assert row is not None
    assert row["strategy"] == "paragraph"


@pytest.mark.asyncio
async def test_chunking_configs_rejects_unknown_strategy(
    session_pool: asyncpg.Pool,
) -> None:
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_md_bad")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO chunking_configs "
                "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
                "VALUES ($1, 'unknown_strategy', 2000, 200, 200)",
                ws_id,
            )
```

### Step 3 : Lancer (rouge)

```
cd backend && TEST_POSTGRES_HOST=192.168.10.171 TEST_POSTGRES_PORT=5432 TEST_POSTGRES_USER=rag TEST_POSTGRES_PASSWORD=jQSKUdhlLghgQ2slb85WTRN1cBMCqqJe uv run pytest tests/integration/test_migration_014_chunking_strategy_markdown.py -v
```

Expected : `test_chunking_configs_accepts_markdown_strategy` ÉCHOUE avec `CheckViolationError` (la stratégie `markdown` est rejetée par la CHECK actuelle). Les autres tests passent.

### Step 4 : Ajouter la dépendance markdown-it-py

Dans `backend/pyproject.toml`, ajouter dans la liste `dependencies` (après `pgvector`) :

```toml
    "markdown-it-py>=3.0,<4.0",
```

Lancer :

```
cd backend && uv sync
```

Expected : `markdown-it-py` installé.

### Step 5 : Écrire la migration

`backend/migrations/014_chunking_strategy_markdown.sql` :

```sql
-- Migration 014 — chunking_configs.strategy : ajout de 'markdown'
--
-- Symétrique à 013 (widening de CHECK constraint).
-- Permet à la stratégie 'markdown' (M9c) d'être stockée. Les extras pour
-- markdown sont validés au niveau Pydantic ({heading_levels: int[]}), pas SQL.

ALTER TABLE chunking_configs DROP CONSTRAINT chunking_configs_strategy_check;
ALTER TABLE chunking_configs ADD CONSTRAINT chunking_configs_strategy_check
    CHECK (strategy IN ('paragraph', 'markdown'));
```

Si le step 1 a révélé un autre nom de contrainte, l'utiliser dans le DROP/ADD.

### Step 6 : Lancer (vert)

```
cd backend && TEST_POSTGRES_HOST=192.168.10.171 TEST_POSTGRES_PORT=5432 TEST_POSTGRES_USER=rag TEST_POSTGRES_PASSWORD=jQSKUdhlLghgQ2slb85WTRN1cBMCqqJe uv run pytest tests/integration/test_migration_014_chunking_strategy_markdown.py -v
```

Expected : 3 tests PASS.

### Step 7 : Lint + format

```
cd backend && uv run ruff check src/ tests/
cd backend && uv run ruff format src/ tests/ --check
```

### Step 8 : Commit

```bash
git add backend/pyproject.toml backend/uv.lock backend/migrations/014_chunking_strategy_markdown.sql backend/tests/integration/test_migration_014_chunking_strategy_markdown.py
git commit -m "feat(M9c-T1): dependance markdown-it-py + migration 014 chunking strategy markdown"
```

---

## Task 2 — DTO `ChunkingConfigSpec` étendue + validator dispatché

**Files:**
- Modify: `backend/src/rag/schemas/admin.py`
- Modify: `backend/tests/unit/schemas/test_chunking_config_schema.py`

### Step 1 : Écrire les tests (rouge)

Ajouter à la fin de `backend/tests/unit/schemas/test_chunking_config_schema.py` :

```python
class TestMarkdownStrategy:
    def test_happy_path_default_extras(self) -> None:
        """extras={} accepté, normalisé en {heading_levels:[1,2]}."""
        spec = ChunkingConfigSpec(
            strategy="markdown", max_chars=2000, min_chars=200,
            overlap_chars=200, extras={},
        )
        assert spec.strategy == "markdown"
        assert spec.extras == {"heading_levels": [1, 2]}

    def test_custom_heading_levels(self) -> None:
        spec = ChunkingConfigSpec(
            strategy="markdown", max_chars=2000, min_chars=200,
            overlap_chars=200, extras={"heading_levels": [1, 2, 3]},
        )
        assert spec.extras == {"heading_levels": [1, 2, 3]}

    def test_rejects_unknown_extras_key(self) -> None:
        with pytest.raises(ValidationError, match="unknown keys"):
            ChunkingConfigSpec(
                strategy="markdown", max_chars=2000, min_chars=200,
                overlap_chars=200, extras={"foo": "bar"},
            )

    def test_rejects_empty_heading_levels(self) -> None:
        with pytest.raises(ValidationError, match="non-empty list"):
            ChunkingConfigSpec(
                strategy="markdown", max_chars=2000, min_chars=200,
                overlap_chars=200, extras={"heading_levels": []},
            )

    def test_rejects_out_of_range_levels(self) -> None:
        with pytest.raises(ValidationError, match=r"in \[1, 6\]"):
            ChunkingConfigSpec(
                strategy="markdown", max_chars=2000, min_chars=200,
                overlap_chars=200, extras={"heading_levels": [0]},
            )
        with pytest.raises(ValidationError, match=r"in \[1, 6\]"):
            ChunkingConfigSpec(
                strategy="markdown", max_chars=2000, min_chars=200,
                overlap_chars=200, extras={"heading_levels": [7]},
            )

    def test_rejects_unsorted_levels(self) -> None:
        with pytest.raises(ValidationError, match="sorted ascending"):
            ChunkingConfigSpec(
                strategy="markdown", max_chars=2000, min_chars=200,
                overlap_chars=200, extras={"heading_levels": [2, 1]},
            )

    def test_rejects_duplicate_levels(self) -> None:
        with pytest.raises(ValidationError, match="duplicates"):
            ChunkingConfigSpec(
                strategy="markdown", max_chars=2000, min_chars=200,
                overlap_chars=200, extras={"heading_levels": [1, 1]},
            )
```

### Step 2 : Lancer (rouge)

```
cd backend && uv run pytest tests/unit/schemas/test_chunking_config_schema.py -v
```

Expected : tous les anciens tests `paragraph` passent ; les 7 nouveaux échouent (validation `markdown` pas implémentée ; le `strategy` accepte seulement `"paragraph"`).

### Step 3 : Étendre le DTO

Dans `backend/src/rag/schemas/admin.py`, trouver `ChunkingConfigSpec` et modifier le champ `strategy` :

```python
# Avant :
# strategy: Literal["paragraph"]

# Après :
strategy: Literal["paragraph", "markdown"]
```

Renommer le validator `_extras_empty_for_paragraph` en `_validate_extras` et le réécrire pour dispatcher :

```python
@field_validator("extras")
@classmethod
def _validate_extras(
    cls, v: dict[str, Any], info: ValidationInfo,
) -> dict[str, Any]:
    strategy = info.data.get("strategy")
    if strategy == "paragraph":
        if v:
            raise ValueError("extras must be empty for strategy 'paragraph'")
        return v
    if strategy == "markdown":
        return _validate_markdown_extras(v)
    return v
```

Ajouter le helper module-level `_validate_markdown_extras` (juste avant la classe `ChunkingConfigSpec` ou à la fin du fichier) :

```python
def _validate_markdown_extras(v: dict[str, Any]) -> dict[str, Any]:
    """Accepte uniquement {heading_levels?: list[int]}. Default si absent."""
    allowed_keys = {"heading_levels"}
    extra_keys = set(v.keys()) - allowed_keys
    if extra_keys:
        raise ValueError(
            f"markdown strategy only accepts {allowed_keys}, got unknown keys: {extra_keys}"
        )
    levels = v.get("heading_levels", [1, 2])
    if not isinstance(levels, list) or not levels:
        raise ValueError("heading_levels must be a non-empty list")
    if not all(isinstance(x, int) and 1 <= x <= 6 for x in levels):
        raise ValueError("heading_levels values must be integers in [1, 6]")
    if levels != sorted(levels):
        raise ValueError("heading_levels must be sorted ascending")
    if len(set(levels)) != len(levels):
        raise ValueError("heading_levels must not contain duplicates")
    return {"heading_levels": levels}
```

### Step 4 : Lancer (vert)

```
cd backend && uv run pytest tests/unit/schemas/test_chunking_config_schema.py -v
```

Expected : tous les tests passent (anciens paragraph + 7 nouveaux markdown).

### Step 5 : mypy + lint + format

```
cd backend && uv run mypy src/rag/schemas/admin.py
cd backend && uv run ruff check src/rag/schemas/admin.py tests/unit/schemas/test_chunking_config_schema.py
cd backend && uv run ruff format src/rag/schemas/admin.py tests/unit/schemas/test_chunking_config_schema.py --check
```

### Step 6 : Commit

```bash
git add backend/src/rag/schemas/admin.py backend/tests/unit/schemas/test_chunking_config_schema.py
git commit -m "feat(M9c-T2): ChunkingConfigSpec accepte strategy markdown + validation extras dispatchee"
```

---

## Task 3 — `MarkdownChunker` (algorithme + tests unitaires)

**Files:**
- Create: `backend/src/rag/indexer/chunking/markdown.py`
- Create: `backend/tests/unit/indexer/test_chunking_markdown.py`

### Step 1 : Écrire les tests (rouge)

`backend/tests/unit/indexer/test_chunking_markdown.py` :

```python
from __future__ import annotations

import json

import pytest

from rag.indexer.chunking import Chunk, MarkdownChunker


def _default(heading_levels: tuple[int, ...] = (1, 2)) -> MarkdownChunker:
    return MarkdownChunker(
        max_chars=2000,
        min_chars=200,
        overlap_chars=200,
        heading_levels=heading_levels,
    )


# ─── Cas de base ─────────────────────────────────────────────────────────────

def test_empty_returns_empty() -> None:
    assert _default().chunk("") == []


def test_no_heading_falls_back_to_paragraph() -> None:
    """Texte sans `#` → délègue à ParagraphChunker. Metadata = valeur neutre."""
    content = "Just plain text.\n\nAnother paragraph."
    result = _default().chunk(content)
    assert len(result) == 1
    assert result[0].metadata == {
        "section_title": None,
        "section_path": [],
        "heading_level": 0,
    }


def test_single_h1_section_returns_one_chunk() -> None:
    content = "# Title\n\nContent of the section."
    result = _default().chunk(content)
    assert len(result) == 1
    chunk = result[0]
    assert chunk.metadata == {
        "section_title": "Title",
        "section_path": [],
        "heading_level": 1,
    }
    assert "Title" in chunk.content
    assert "Content of the section" in chunk.content


def test_h1_h2_split_with_default_heading_levels() -> None:
    """# A\n## B\n## C → 3 chunks distincts."""
    content = "# A\n\nAlpha content.\n\n## B\n\nBravo content.\n\n## C\n\nCharlie content."
    result = _default().chunk(content)
    assert len(result) == 3
    titles = [c.metadata["section_title"] for c in result]
    assert titles == ["A", "B", "C"]
    levels = [c.metadata["heading_level"] for c in result]
    assert levels == [1, 2, 2]


# ─── Breadcrumb ──────────────────────────────────────────────────────────────

def test_section_path_captures_parent_headings_inside_levels() -> None:
    content = "# Doc\n\nIntro.\n\n## Install\n\nInstall details."
    result = _default(heading_levels=(1, 2)).chunk(content)
    # 2 sections : "Doc" et "Install"
    install = next(c for c in result if c.metadata["section_title"] == "Install")
    assert install.metadata["section_path"] == ["Doc"]


def test_section_path_captures_parents_outside_levels() -> None:
    """H3 enrichit le breadcrumb même s'il ne déclenche pas de split."""
    content = (
        "# Doc\n\n"
        "Intro.\n\n"
        "## Install\n\n"
        "Top install.\n\n"
        "### Linux\n\n"
        "Linux content."
    )
    result = _default(heading_levels=(1, 2)).chunk(content)
    install = next(c for c in result if c.metadata["section_title"] == "Install")
    # Le H3 "Linux" est absorbé dans la section H2 "Install"
    assert install.metadata["section_path"] == ["Doc"]
    assert "Linux" in install.content


def test_preamble_text_before_first_heading() -> None:
    content = "Intro freely written.\n\n# Doc\n\nDoc content."
    result = _default().chunk(content)
    assert len(result) == 2
    preamble = result[0]
    assert preamble.metadata == {
        "section_title": None,
        "section_path": [],
        "heading_level": 0,
    }
    assert "Intro freely written" in preamble.content


# ─── Sub-split de section longue ────────────────────────────────────────────

def test_long_section_subsplit_preserves_metadata() -> None:
    """Section > max_chars → plusieurs chunks partagent la metadata."""
    big_para = "Paragraph content. " * 200  # ~3800 chars
    content = f"# Big\n\n{big_para}"
    result = _default().chunk(content)
    assert len(result) >= 2
    for chunk in result:
        assert chunk.metadata["section_title"] == "Big"
        assert chunk.metadata["heading_level"] == 1


def test_subsplit_does_not_cut_inside_fence() -> None:
    """Une section longue avec un fence : le fence reste atomique."""
    big_intro = "Intro text. " * 100  # ~1200 chars
    fence = "```python\n" + "x = 1\n" * 100 + "```"  # ~700 chars
    content = f"# Section\n\n{big_intro}\n\n{fence}\n\nMore text."
    result = _default().chunk(content)
    # Vérifie qu'un chunk contient le fence complet (ouverture + fermeture intactes)
    found_fence_chunk = False
    for chunk in result:
        if "```python" in chunk.content:
            assert "```" in chunk.content[chunk.content.index("```python") + 9:], (
                f"fence non terminé dans chunk: {chunk.content[:200]}..."
            )
            found_fence_chunk = True
    assert found_fence_chunk, "aucun chunk ne contient le fence"


def test_giant_fence_exceeds_max_chars_kept_intact() -> None:
    """Fence seul > max_chars → 1 chunk hors-borne, pas de split brutal."""
    giant_fence = "```\n" + "y = 2\n" * 500 + "```"  # ~3500 chars > 2000
    content = f"# Huge\n\nIntro.\n\n{giant_fence}"
    result = _default().chunk(content)
    # Au moins un chunk contient le fence complet (entre ``` et ```)
    fence_chunks = [c for c in result if "```" in c.content and c.content.count("```") >= 2]
    assert len(fence_chunks) >= 1


# ─── Configuration heading_levels ───────────────────────────────────────────

def test_heading_levels_only_h1_groups_subsections() -> None:
    """heading_levels=(1,) → H2 absorbées dans la section H1."""
    content = "# A\n\nAlpha.\n\n## a1\n\nOne.\n\n## a2\n\nTwo."
    result = _default(heading_levels=(1,)).chunk(content)
    assert len(result) == 1
    assert result[0].metadata["section_title"] == "A"
    assert "a1" in result[0].content
    assert "a2" in result[0].content


def test_heading_levels_h1_h2_h3() -> None:
    """heading_levels=(1,2,3) → split à chaque H3."""
    content = (
        "# Doc\n\nIntro.\n\n"
        "## Install\n\nTop.\n\n"
        "### From source\n\nDetails."
    )
    result = _default(heading_levels=(1, 2, 3)).chunk(content)
    titles = [c.metadata["section_title"] for c in result]
    assert "From source" in titles
    from_source = next(c for c in result if c.metadata["section_title"] == "From source")
    assert from_source.metadata["section_path"] == ["Doc", "Install"]
    assert from_source.metadata["heading_level"] == 3


def test_heading_levels_h3_only() -> None:
    """heading_levels=(3,) avec H1 et H3 → H1 devient préambule, H3 splits."""
    content = "# Top\n\nTop content.\n\n### Sub\n\nSub content."
    result = _default(heading_levels=(3,)).chunk(content)
    assert len(result) >= 1
    sub_chunks = [c for c in result if c.metadata.get("section_title") == "Sub"]
    assert len(sub_chunks) == 1
    # Le breadcrumb capture quand même le H1 parent
    assert sub_chunks[0].metadata["section_path"] == ["Top"]


# ─── Contrats metadata ──────────────────────────────────────────────────────

def test_metadata_keys_exact_set() -> None:
    """Tous les chunks ont exactement {section_title, section_path, heading_level}."""
    content = "Preamble.\n\n# A\n\nText.\n\n## B\n\nMore."
    result = _default().chunk(content)
    expected_keys = {"section_title", "section_path", "heading_level"}
    for chunk in result:
        assert set(chunk.metadata.keys()) == expected_keys, (
            f"keys mismatch: {set(chunk.metadata.keys())} != {expected_keys}"
        )


def test_metadata_json_serializable() -> None:
    content = "# Title\n\nContent."
    result = _default().chunk(content)
    for chunk in result:
        # Doit pouvoir être sérialisé sans erreur (dict() pour convertir Mapping)
        json.dumps(dict(chunk.metadata))


# ─── Robustesse Markdown malformé ───────────────────────────────────────────

def test_unclosed_fence_does_not_crash() -> None:
    """Fence non clôturé → parser le traite comme texte, pas de crash."""
    content = "# Title\n\n```python\nx = 1\n# pas de fermeture"
    result = _default().chunk(content)
    assert len(result) >= 1  # ne crash pas
    assert result[0].metadata["section_title"] == "Title"


def test_setext_heading_supported() -> None:
    """Headings setext (Title\\n=====) sont reconnus par markdown-it-py."""
    content = "Title\n=====\n\nContent."
    result = _default().chunk(content)
    # Le setext H1 doit déclencher une section
    titles = [c.metadata.get("section_title") for c in result]
    assert "Title" in titles
```

### Step 2 : Lancer (rouge)

```
cd backend && uv run pytest tests/unit/indexer/test_chunking_markdown.py -v
```

Expected : `ImportError: cannot import name 'MarkdownChunker' from 'rag.indexer.chunking'`.

### Step 3 : Écrire `MarkdownChunker`

`backend/src/rag/indexer/chunking/markdown.py` :

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token

from rag.indexer.chunking.paragraph import ParagraphChunker
from rag.indexer.chunking.protocol import Chunk

_NEUTRAL_METADATA: dict[str, Any] = {
    "section_title": None,
    "section_path": [],
    "heading_level": 0,
}


@dataclass
class _Section:
    """Section interne du chunker. Jamais exposée hors du module."""

    title: str | None
    path: list[str]
    level: int
    content: str
    fence_ranges: list[tuple[int, int]] = field(default_factory=list)


class MarkdownChunker:
    """Découpe un document Markdown par sections H{n} avec respect des fences.

    Algorithme :
      1. Parse via markdown-it-py.
      2. Découpe en sections sur les tokens heading_open dont le niveau est
         dans heading_levels.
      3. Pour chaque section, sub-split si > max_chars en préservant les fences.
      4. Cas particulier : aucun heading aux niveaux configurés → délègue
         à ParagraphChunker, metadata neutre.
      5. Préambule (texte avant 1er heading) → section "fictive" avec
         section_title=None, heading_level=0.
    """

    def __init__(
        self,
        *,
        max_chars: int,
        min_chars: int,
        overlap_chars: int,
        heading_levels: tuple[int, ...],
    ) -> None:
        self._max_chars = max_chars
        self._min_chars = min_chars
        self._overlap_chars = overlap_chars
        self._heading_levels = heading_levels
        self._md = MarkdownIt("commonmark")
        self._paragraph_fallback = ParagraphChunker(
            max_chars=max_chars,
            min_chars=min_chars,
            overlap_chars=overlap_chars,
        )

    def chunk(self, content: str) -> list[Chunk]:
        if not content.strip():
            return []
        sections = self._split_into_sections(content)
        if not sections:
            return self._enrich_with_neutral_metadata(
                self._paragraph_fallback.chunk(content),
            )
        result: list[Chunk] = []
        for section in sections:
            result.extend(self._chunk_section(section))
        return result

    @staticmethod
    def _enrich_with_neutral_metadata(chunks: list[Chunk]) -> list[Chunk]:
        return [Chunk(content=c.content, metadata=_NEUTRAL_METADATA) for c in chunks]

    def _split_into_sections(self, content: str) -> list[_Section]:
        tokens = self._md.parse(content)
        lines = content.splitlines(keepends=False)
        sections: list[_Section] = []
        breadcrumb: list[tuple[int, str]] = []  # (level, title)
        current_start_line: int | None = None
        current_meta: tuple[str | None, list[str], int] | None = None
        fences: list[tuple[int, int]] = []

        def flush_section(end_line: int) -> None:
            nonlocal current_start_line, current_meta, fences
            if current_start_line is None or current_meta is None:
                return
            section_text = "\n".join(lines[current_start_line:end_line])
            title, path, level = current_meta
            sections.append(
                _Section(
                    title=title,
                    path=path,
                    level=level,
                    content=section_text,
                    fence_ranges=fences,
                ),
            )
            fences = []

        for i, tok in enumerate(tokens):
            if tok.type == "heading_open":
                heading_level = int(tok.tag[1])  # h1 → 1, h2 → 2, ...
                # Extract title from next inline token
                title = self._extract_heading_title(tokens, i)
                # Update breadcrumb : pop tous les niveaux >= heading_level
                while breadcrumb and breadcrumb[-1][0] >= heading_level:
                    breadcrumb.pop()
                breadcrumb.append((heading_level, title))

                if heading_level in self._heading_levels:
                    # Flush la section courante
                    start_line = tok.map[0] if tok.map else 0
                    flush_section(start_line)
                    # Démarrer une nouvelle section
                    current_start_line = start_line
                    current_meta = (title, [t for _, t in breadcrumb[:-1]], heading_level)
                    fences = []
            elif tok.type == "fence" and tok.map and current_meta is not None:
                # Track la position du fence dans la section courante
                # (positions absolues dans `lines`)
                fences.append((tok.map[0], tok.map[1]))

        # Préambule (texte avant le 1er heading déclencheur)
        if sections:
            first_section_line = sections[0].content.splitlines()[0] if sections[0].content else ""
            # Chercher l'index dans lines original
            # Cas simple : si le contenu de la 1re section commence à line N > 0,
            # alors lines[0:N] est le préambule
            pre_lines = self._find_preamble_lines(lines, sections[0])
            if pre_lines.strip():
                sections.insert(
                    0,
                    _Section(
                        title=None,
                        path=[],
                        level=0,
                        content=pre_lines,
                        fence_ranges=[],
                    ),
                )

        # Flush la dernière section (jusqu'à la fin du document)
        if current_start_line is not None:
            flush_section(len(lines))

        return sections

    @staticmethod
    def _extract_heading_title(tokens: list[Token], heading_open_index: int) -> str:
        """Le token inline suit immédiatement le heading_open."""
        if heading_open_index + 1 < len(tokens):
            inline_tok = tokens[heading_open_index + 1]
            if inline_tok.type == "inline" and inline_tok.content:
                return inline_tok.content.strip()
        return ""

    @staticmethod
    def _find_preamble_lines(lines: list[str], first_section: _Section) -> str:
        """Le préambule est tout ce qui précède le début de la 1re section."""
        # On cherche la 1re ligne du contenu de first_section dans lines.
        if not first_section.content:
            return ""
        first_line = first_section.content.splitlines()[0]
        for idx, line in enumerate(lines):
            if line == first_line:
                return "\n".join(lines[:idx])
        return ""

    def _chunk_section(self, section: _Section) -> list[Chunk]:
        meta: dict[str, Any] = {
            "section_title": section.title,
            "section_path": section.path,
            "heading_level": section.level,
        }
        if len(section.content) <= self._max_chars:
            return [Chunk(content=section.content, metadata=meta)]
        # Sub-split en préservant les fences
        return self._subsplit_with_fences(section, meta)

    def _subsplit_with_fences(
        self, section: _Section, meta: dict[str, Any],
    ) -> list[Chunk]:
        """Découpe une section longue en alternant text_blocks et fence_blocks.

        Les fence_blocks restent atomiques (1 chunk, même si > max_chars).
        Les text_blocks > max_chars sont délégués à ParagraphChunker, puis
        chaque chunk produit est ré-emballé avec la metadata de la section.
        """
        section_lines = section.content.splitlines(keepends=False)
        if not section.fence_ranges:
            # Pas de fence dans cette section : tout est du texte
            return self._chunks_from_text_block(section.content, meta)

        # Convertir les fence_ranges (positions absolues dans le doc original)
        # en positions relatives à section_lines
        # Le contenu de la section commence à la ligne `section_start_in_doc`
        # On retrouve cette ligne en cherchant la 1re ligne du contenu de la
        # section dans `section_lines` — c'est forcément `section_lines[0]`,
        # donc la conversion = soustraire l'offset du début de section.
        section_first_line_in_doc = section.fence_ranges[0][0]  # approximation
        # Approche plus robuste : on stocke en _Section la position de départ
        # absolue. Refactor minimal ici : recalcule l'offset.

        # Trouver le 1er fence : la position absolue dans le doc.
        # On reconstruit en termes de lignes de section :
        # - On a section.content qui est join(\n) de N lignes
        # - Le premier fence dans le doc est à fence_ranges[0]
        # On ne connait pas l'offset absolu de section dans le doc — il faut
        # le passer via _Section. Mais on peut faire plus simple : itérer
        # sur section_lines et identifier les positions de fences par scan.

        # Simplification : scan régex des lignes de section pour trouver les fences
        fence_ranges_rel = self._scan_fences_in_lines(section_lines)
        if not fence_ranges_rel:
            return self._chunks_from_text_block(section.content, meta)

        chunks: list[Chunk] = []
        cursor = 0
        for fence_start, fence_end in fence_ranges_rel:
            # Text block avant ce fence
            if cursor < fence_start:
                text_lines = section_lines[cursor:fence_start]
                text_block = "\n".join(text_lines).strip()
                if text_block:
                    chunks.extend(self._chunks_from_text_block(text_block, meta))
            # Fence block (atomique)
            fence_lines = section_lines[fence_start:fence_end]
            fence_text = "\n".join(fence_lines)
            chunks.append(Chunk(content=fence_text, metadata=meta))
            cursor = fence_end

        # Reste après le dernier fence
        if cursor < len(section_lines):
            tail_lines = section_lines[cursor:]
            tail_text = "\n".join(tail_lines).strip()
            if tail_text:
                chunks.extend(self._chunks_from_text_block(tail_text, meta))

        return chunks

    @staticmethod
    def _scan_fences_in_lines(lines: list[str]) -> list[tuple[int, int]]:
        """Scan régex des lignes pour identifier les positions des fences.

        Retourne une liste de tuples (start_line, end_line_exclusive).
        Un fence est délimité par une ligne commençant par ``` (ou ~~~).
        """
        ranges: list[tuple[int, int]] = []
        in_fence = False
        fence_marker = ""
        start = 0
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if not in_fence and (stripped.startswith("```") or stripped.startswith("~~~")):
                in_fence = True
                fence_marker = stripped[:3]
                start = i
            elif in_fence and stripped.startswith(fence_marker):
                ranges.append((start, i + 1))
                in_fence = False
        if in_fence:
            # Fence non clôturé : on l'inclut jusqu'à la fin (cas malformé)
            ranges.append((start, len(lines)))
        return ranges

    def _chunks_from_text_block(
        self, text: str, meta: dict[str, Any],
    ) -> list[Chunk]:
        """Délègue un text_block à ParagraphChunker et ré-emballe avec metadata."""
        sub_chunks = self._paragraph_fallback.chunk(text)
        return [Chunk(content=c.content, metadata=meta) for c in sub_chunks]
```

### Step 4 : Modifier `chunking/__init__.py` pour exporter

`backend/src/rag/indexer/chunking/__init__.py` :

```python
from __future__ import annotations

from rag.indexer.chunking.factory import make_chunker
from rag.indexer.chunking.markdown import MarkdownChunker
from rag.indexer.chunking.paragraph import ParagraphChunker
from rag.indexer.chunking.protocol import Chunk, ChunkerProtocol

__all__ = [
    "Chunk",
    "ChunkerProtocol",
    "MarkdownChunker",
    "ParagraphChunker",
    "make_chunker",
]
```

### Step 5 : Lancer (vert)

```
cd backend && uv run pytest tests/unit/indexer/test_chunking_markdown.py -v
```

Expected : 17 PASS. Si certains échouent, debug l'algorithme.

### Step 6 : mypy + lint + format

```
cd backend && uv run mypy src/rag/indexer/chunking/markdown.py
cd backend && uv run ruff check src/rag/indexer/chunking/ tests/unit/indexer/test_chunking_markdown.py
cd backend && uv run ruff format src/rag/indexer/chunking/ tests/unit/indexer/test_chunking_markdown.py --check
```

### Step 7 : Commit

```bash
git add backend/src/rag/indexer/chunking/markdown.py backend/src/rag/indexer/chunking/__init__.py backend/tests/unit/indexer/test_chunking_markdown.py
git commit -m "feat(M9c-T3): MarkdownChunker + 17 tests unitaires"
```

---

## Task 4 — Factory `make_chunker` étendue

**Files:**
- Modify: `backend/src/rag/indexer/chunking/factory.py`
- Modify: `backend/tests/unit/indexer/test_chunking_factory.py`

### Step 1 : Écrire les tests (rouge)

Ajouter à la fin de `backend/tests/unit/indexer/test_chunking_factory.py` :

```python
def test_make_chunker_markdown_returns_markdown_chunker() -> None:
    from rag.indexer.chunking import MarkdownChunker
    chunker = make_chunker(
        strategy="markdown",
        max_chars=2000, min_chars=200, overlap_chars=200,
        extras={"heading_levels": [1, 2]},
    )
    assert isinstance(chunker, MarkdownChunker)


def test_make_chunker_markdown_default_heading_levels() -> None:
    """extras={} → heading_levels=(1,2) par défaut."""
    chunker = make_chunker(
        strategy="markdown",
        max_chars=2000, min_chars=200, overlap_chars=200,
        extras={},
    )
    # Comportement observable : H1 + H2 doivent split, H3 pas
    content = "# A\n\nAlpha.\n\n## B\n\nBravo.\n\n### C\n\nCharlie."
    result = chunker.chunk(content)
    titles = [c.metadata["section_title"] for c in result]
    assert "A" in titles
    assert "B" in titles
    assert "C" not in titles  # H3 absorbé dans B


def test_make_chunker_markdown_custom_heading_levels() -> None:
    chunker = make_chunker(
        strategy="markdown",
        max_chars=2000, min_chars=200, overlap_chars=200,
        extras={"heading_levels": [1, 2, 3]},
    )
    content = "# A\n\nAlpha.\n\n## B\n\nBravo.\n\n### C\n\nCharlie."
    result = chunker.chunk(content)
    titles = [c.metadata["section_title"] for c in result]
    assert "C" in titles  # H3 doit déclencher un split


def test_make_chunker_markdown_rejects_unknown_extras_key() -> None:
    with pytest.raises(ValueError, match="unknown extras keys"):
        make_chunker(
            strategy="markdown",
            max_chars=2000, min_chars=200, overlap_chars=200,
            extras={"foo": "bar"},
        )


def test_make_chunker_markdown_immutable_levels() -> None:
    """heading_levels est stocké en tuple (immutable)."""
    from rag.indexer.chunking.markdown import MarkdownChunker
    chunker = make_chunker(
        strategy="markdown",
        max_chars=2000, min_chars=200, overlap_chars=200,
        extras={"heading_levels": [1, 2]},
    )
    assert isinstance(chunker, MarkdownChunker)
    # Accès au champ privé pour vérifier le type immutable
    assert isinstance(chunker._heading_levels, tuple)
```

### Step 2 : Lancer (rouge)

```
cd backend && uv run pytest tests/unit/indexer/test_chunking_factory.py -v
```

Expected : les nouveaux tests `markdown` échouent (`ValueError: unknown chunking strategy: markdown`).

### Step 3 : Étendre la factory

Modifier `backend/src/rag/indexer/chunking/factory.py` :

```python
from __future__ import annotations

from typing import Any

from rag.indexer.chunking.markdown import MarkdownChunker
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
    """Construit un chunker selon la stratégie configurée.

    `extras` est un dict opaque réservé aux stratégies qui en ont besoin ;
    doit être vide pour 'paragraph', accepte {heading_levels: int[]} pour
    'markdown' (default [1, 2]).

    Lève `ValueError` si la stratégie est inconnue ou si les extras sont
    invalides pour la stratégie choisie.
    """
    if strategy == "paragraph":
        if extras:
            raise ValueError(f"paragraph strategy does not accept extras (got {extras!r})")
        return ParagraphChunker(
            max_chars=max_chars,
            min_chars=min_chars,
            overlap_chars=overlap_chars,
        )
    if strategy == "markdown":
        return _make_markdown_chunker(
            max_chars=max_chars,
            min_chars=min_chars,
            overlap_chars=overlap_chars,
            extras=extras,
        )
    raise ValueError(f"unknown chunking strategy: {strategy}")


def _make_markdown_chunker(
    *,
    max_chars: int,
    min_chars: int,
    overlap_chars: int,
    extras: dict[str, Any],
) -> MarkdownChunker:
    """Construit un MarkdownChunker. Validation défensive des extras
    (déjà fait au niveau Pydantic, mais le factory peut être appelé hors
    API ex: tests).
    """
    allowed = {"heading_levels"}
    unknown = set(extras.keys()) - allowed
    if unknown:
        raise ValueError(f"markdown strategy unknown extras keys: {unknown}")
    heading_levels = extras.get("heading_levels", [1, 2])
    return MarkdownChunker(
        max_chars=max_chars,
        min_chars=min_chars,
        overlap_chars=overlap_chars,
        heading_levels=tuple(heading_levels),
    )
```

### Step 4 : Lancer (vert)

```
cd backend && uv run pytest tests/unit/indexer/test_chunking_factory.py -v
```

Expected : tous tests passent (anciens + 5 nouveaux).

### Step 5 : Sanity check — full unit indexer

```
cd backend && uv run pytest tests/unit/indexer/ -v
```

Expected : tous les tests `paragraph` + `factory` + `markdown` passent.

### Step 6 : Lint + format

```
cd backend && uv run ruff check src/rag/indexer/chunking/factory.py tests/unit/indexer/test_chunking_factory.py
cd backend && uv run ruff format src/rag/indexer/chunking/factory.py tests/unit/indexer/test_chunking_factory.py --check
```

### Step 7 : Commit

```bash
git add backend/src/rag/indexer/chunking/factory.py backend/tests/unit/indexer/test_chunking_factory.py
git commit -m "feat(M9c-T4): make_chunker dispatch sur markdown + 5 tests factory"
```

---

## Task 5 — Test end-to-end RealIndexer + markdown

**Files:**
- Create: `backend/tests/integration/test_real_indexer_markdown.py`

### Step 1 : Écrire le test (rouge)

`backend/tests/integration/test_real_indexer_markdown.py` :

```python
from __future__ import annotations

import json

import asyncpg
import pytest

from rag.db.pool import WorkspacePoolRegistry
from rag.db.workspace_schema import derive_workspace_dsn, drop_workspace_database
from rag.indexer.real import RealIndexer
from rag.schemas.admin import IndexerSpec, WorkspaceCreateRequest
from rag.services.workspaces import create_workspace


README_DEMO = """\
Welcome to the demo project.

# Installation

Install the package via pip.

## From PyPI

```bash
pip install demo
```

## From source

Clone the repo and run setup.

# Usage

Basic usage example.

```python
import demo
demo.run()
```

# Reference

API reference is auto-generated.
"""


class _StubProvider:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


class _StubClient:
    async def get_default_vault_name(self) -> str | None:
        return None


@pytest.mark.asyncio
async def test_real_indexer_markdown_strategy_produces_section_metadata(
    migrated: asyncpg.Pool, admin_dsn: str, pg_container: str,
) -> None:
    """End-to-end : workspace configuré en markdown → chunks ont la metadata."""
    req = WorkspaceCreateRequest(
        name="ws_md_e2e",
        indexer=IndexerSpec(
            provider="ollama", model="mxbai-embed-large",
            api_key_ref=None, base_url="http://stub:11434",
        ),
    )
    ws = await create_workspace(
        request=req,
        config_pool=migrated,
        admin_dsn=admin_dsn,
        resolver=None,  # type: ignore[arg-type]
        default_vault_name=None,
        api_key_dek="x" * 32,
    )
    rag_base = await migrated.fetchval(
        "SELECT rag_base FROM workspaces WHERE id = $1", ws["id"],
    )

    registry: WorkspacePoolRegistry | None = None
    try:
        # Reconfigure le workspace en markdown
        await migrated.execute(
            "UPDATE chunking_configs SET strategy=$1, extras=$2::jsonb "
            "WHERE workspace_id = $3",
            "markdown",
            json.dumps({"heading_levels": [1, 2]}),
            ws["id"],
        )

        # Recrée embeddings avec dim=8 pour matcher le stub
        ws_dsn = derive_workspace_dsn(admin_dsn, rag_base)
        conn = await asyncpg.connect(ws_dsn)
        try:
            await conn.execute("DROP TABLE IF EXISTS embeddings CASCADE")
            await conn.execute(
                "CREATE TABLE embeddings ("
                "id SERIAL PRIMARY KEY, path TEXT NOT NULL, "
                "chunk_index INT NOT NULL, content TEXT NOT NULL, "
                "embedding vector(8) NOT NULL, "
                "metadata JSONB NOT NULL DEFAULT '{}'::jsonb, "
                "indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "UNIQUE (path, chunk_index))"
            )
        finally:
            await conn.close()

        registry = WorkspacePoolRegistry(
            config_dsn=pg_container, admin_dsn=admin_dsn,
        )
        await registry.start()

        indexer = RealIndexer(
            config_pool=migrated,
            pool_registry=registry,
            secret_resolver=None,  # type: ignore[arg-type]
            client_provider=_StubClient(),
            provider_factory=lambda **kw: _StubProvider(),
        )

        nb = await indexer.index_file(
            workspace_id=ws["id"],
            path="README.md",
            content=README_DEMO,
            content_hash="sha256:demo",
            indexer_used="ollama/mxbai-embed-large",
        )
        # Au moins 4 sections : préambule + Installation + Usage + Reference
        assert nb >= 4

        # Vérifier la metadata stockée
        conn = await asyncpg.connect(ws_dsn)
        try:
            rows = await conn.fetch(
                "SELECT chunk_index, content, metadata FROM embeddings "
                "WHERE path = 'README.md' ORDER BY chunk_index",
            )
        finally:
            await conn.close()

        for row in rows:
            meta_raw = row["metadata"]
            meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
            assert set(meta.keys()) == {"section_title", "section_path", "heading_level"}

        # Au moins un chunk a heading_level=1
        levels = []
        for row in rows:
            meta_raw = row["metadata"]
            meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
            levels.append(meta["heading_level"])
        assert 1 in levels
    finally:
        if registry is not None:
            await registry.close_all()
        await drop_workspace_database(admin_dsn, rag_base)
        await migrated.execute(
            "DELETE FROM workspaces WHERE id = $1", ws["id"],
        )
```

### Step 2 : Lancer (rouge → puis vert)

```
cd backend && TEST_POSTGRES_HOST=192.168.10.171 TEST_POSTGRES_PORT=5432 TEST_POSTGRES_USER=rag TEST_POSTGRES_PASSWORD=jQSKUdhlLghgQ2slb85WTRN1cBMCqqJe uv run pytest tests/integration/test_real_indexer_markdown.py -v
```

Le test devrait passer du premier coup vu que toutes les briques précédentes (T1-T4) sont en place. Si échec : debug.

### Step 3 : Lint + format

```
cd backend && uv run ruff check tests/integration/test_real_indexer_markdown.py
cd backend && uv run ruff format tests/integration/test_real_indexer_markdown.py --check
```

### Step 4 : Commit

```bash
git add backend/tests/integration/test_real_indexer_markdown.py
git commit -m "feat(M9c-T5): test e2e RealIndexer + strategy markdown"
```

---

## Task 6 — Roadmap + smoke final

**Files:**
- Modify: `specs/09-roadmap.md`

### Step 1 : Mettre à jour la roadmap

Lire d'abord la section actuelle :

```
grep -A 15 "Amélioration du chunking" specs/09-roadmap.md
```

Remplacer la section par :

```markdown
### Amélioration du chunking

✅ Infrastructure backend livrée en M9 — cf. `docs/superpowers/specs/2026-05-18-M9-backend-chunking-infrastructure-design.md`.
✅ Frontend livré en M9b — onglet `Chunking` dans `WorkspaceDetailPanel`, cf. `docs/superpowers/specs/2026-05-19-M9b-frontend-chunking-design.md`.
✅ Stratégie sémantique `markdown` livrée en M9c — cf. `docs/superpowers/specs/2026-05-19-M9c-backend-markdown-chunker-design.md`. Configurable via API admin (`PUT /chunking-config` avec `strategy='markdown'` + `extras={heading_levels:[1,2]}`). Frontend différé en M9c-front (l'option n'apparaît pas encore dans le Select de l'IHM).

Stratégies disponibles : `paragraph` (M4a), `markdown` (M9c).

Stratégies futures (jalons distincts) :
- M9c-front : exposer `markdown` dans l'IHM workspace
- Chunking par blocs de code (langage-aware) — jalon M9d ou +
- Métadonnées enrichies (content_type, language) — quand un usage concret le justifiera
- Exposition de la metadata via MCP `search()` — quand un client agent en tirera parti
```

### Step 2 : Smoke final — full pytest suite

```
cd backend && TEST_POSTGRES_HOST=192.168.10.171 TEST_POSTGRES_PORT=5432 TEST_POSTGRES_USER=rag TEST_POSTGRES_PASSWORD=jQSKUdhlLghgQ2slb85WTRN1cBMCqqJe uv run pytest -q 2>&1 | tail -10
```

Expected : tous tests verts. Si quelques flaky pré-existants identifiés en M9-T10, OK (déjà documentés).

### Step 3 : mypy global

```
cd backend && uv run mypy src/rag/indexer/chunking/ src/rag/schemas/admin.py
```

Expected : Success.

### Step 4 : Commit

```bash
git add specs/09-roadmap.md
git commit -m "docs(M9c-T6): roadmap marque M9c livre (markdown chunker backend)"
```

---

## Self-review du plan

1. **Couverture spec** :
   - §2 Décisions D1-D10 → toutes implémentées (D1 dans T1, D2 dans T2+T3, D3 dans T3, D4 dans T3, D5+D6 dans T3, D7 dans T3, D8 dans T2, D9 dans T1-T6, D10 = hors-scope explicite)
   - §3 Inventaire fichiers → couverts par T1-T6
   - §4 Schéma extras → T2
   - §5 Migration + factory → T1 (migration) + T4 (factory)
   - §6 Algorithme MarkdownChunker → T3
   - §7 Contrat metadata → vérifié dans T3 tests + T5 e2e
   - §8 Hors-scope MCP → respecté (pas de modif `mcp.py`)
   - §9 Tests → couverture distribuée sur T1-T5
   - §10 Plan de livraison → 6 tâches alignées
   - §11 Risques → mitigés (pin version markdown-it-py en T1, validation défensive en T4, tests robustesse en T3)

2. **Aucun placeholder** : tous les blocs de code sont complets et exécutables.

3. **Cohérence types** :
   - `MarkdownChunker(*, max_chars, min_chars, overlap_chars, heading_levels: tuple)` cohérent dans T3 (impl) et T4 (factory)
   - `_Section` dataclass privé au module markdown.py
   - `Chunk.metadata = {section_title, section_path, heading_level}` cohérent dans T3 (production) + T5 (vérification e2e)
   - `extras = {heading_levels: [1, 2]}` cohérent entre T2 (Pydantic) + T4 (factory) + T5 (config workspace)
   - Convention `heading_levels` stocké en `tuple` immutable côté `MarkdownChunker._heading_levels`, mais reste `list[int]` en JSON dans extras (sérialisation jsonb)
