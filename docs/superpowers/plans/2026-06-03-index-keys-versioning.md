# Index Keys Versioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter la visualisation des clés d'index RAG (paths + chunks + versions) et la stratégie `append`/`replace` par path, configurable via IHM et via `.rag/strategy.yml`.

**Architecture:** Nouvelle table `path_strategies` (config DB) pour stocker la stratégie par path. `upsert_chunks` accepte un paramètre `strategy` — en mode `append` le DELETE est omis. Le sync worker lit `.rag/strategy.yml` après git pull et UPSERT les stratégies en base. Trois endpoints admin `/index-keys` exposent la liste, le détail, et le PATCH de stratégie. Nouvel onglet "Index" dans le workspace detail panel.

**Tech Stack:** Python 3.12 / FastAPI / asyncpg / Pydantic v2 / PyYAML — React 18 / TypeScript strict / TanStack Query / Tailwind / shadcn/ui / i18next / Vitest

---

## Carte des fichiers

### Backend — créations
- `backend/migrations/035_path_strategies.sql`
- `backend/src/rag/db/path_strategies.py`
- `backend/src/rag/db/index_keys.py`
- `backend/src/rag/schemas/index_keys.py`
- `backend/src/rag/api/admin_index_keys.py`
- `backend/src/rag/sync/strategy_config.py`
- `backend/tests/integration/test_path_strategies.py`
- `backend/tests/integration/test_upsert_chunks_strategy.py`
- `backend/tests/unit/test_parse_strategy_file.py`
- `backend/tests/api/test_admin_index_keys.py`

### Backend — modifications
- `backend/src/rag/db/workspace_embeddings.py` (param `strategy`)
- `backend/src/rag/indexer/real.py` (lit stratégie avant upsert)
- `backend/src/rag/sync/executor.py` (appelle strategy_config après git pull)
- `backend/src/rag/main.py` (inclut le nouveau router)

### Frontend — créations
- `frontend/src/hooks/useIndexKeys.ts`
- `frontend/src/pages/workspace/WorkspaceIndexTab.tsx`
- `frontend/src/pages/workspace/__tests__/WorkspaceIndexTab.test.tsx`

### Frontend — modifications
- `frontend/src/lib/workspaces.types.ts` (types IndexKey)
- `frontend/src/lib/workspaces.ts` (appels API index-keys)
- `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx` (onglet Index)
- `frontend/src/i18n/fr/workspace.json` (clés index.*)
- `frontend/src/i18n/en/workspace.json` (clés index.*)

---

## Task 1 — Migration SQL `path_strategies`

**Files:**
- Create: `backend/migrations/035_path_strategies.sql`

- [ ] **Écrire la migration**

```sql
-- Migration 035 — table path_strategies (stratégie de vectorisation par path)
CREATE TABLE path_strategies (
    workspace_id  UUID        NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    path          TEXT        NOT NULL,
    strategy      TEXT        NOT NULL DEFAULT 'replace'
                              CHECK (strategy IN ('replace', 'append')),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by    TEXT        NOT NULL DEFAULT 'ui'
                              CHECK (updated_by IN ('ui', 'strategy_file')),
    PRIMARY KEY (workspace_id, path)
);
```

- [ ] **Appliquer la migration**

```bash
cd backend && uv run python -m rag.db.migrations
```

Résultat attendu : `migration 035_path_strategies.sql applied`

- [ ] **Commit**

```bash
git add backend/migrations/035_path_strategies.sql
git commit -m "chore(db): migration 035 — table path_strategies"
```

---

## Task 2 — DB layer `path_strategies`

**Files:**
- Create: `backend/src/rag/db/path_strategies.py`
- Create: `backend/tests/integration/test_path_strategies.py`

- [ ] **Écrire le test (rouge)**

```python
# backend/tests/integration/test_path_strategies.py
from __future__ import annotations

import uuid
from uuid import UUID

import asyncpg
import pytest
import pytest_asyncio

from rag.db.migrations import run_migrations
from rag.db.path_strategies import get_strategy, upsert_strategy, upsert_strategies_batch


@pytest_asyncio.fixture
async def migrated_pool(pg_container: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(pg_container, min_size=1, max_size=2)
    await run_migrations(pool)
    return pool


@pytest_asyncio.fixture
async def ws_id(migrated_pool: asyncpg.Pool) -> UUID:
    """Insère un workspace minimal et retourne son id."""
    wid = uuid.uuid4()
    async with migrated_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO workspaces (id, name, rag_cnx)
            VALUES ($1, $2, 'postgresql://localhost/rag_test')
            """,
            wid,
            f"ws_{wid.hex[:8]}",
        )
    return wid


@pytest.mark.asyncio
async def test_get_strategy_default_replace(migrated_pool: asyncpg.Pool, ws_id: UUID) -> None:
    result = await get_strategy(migrated_pool, ws_id, "LESSONS.md")
    assert result == "replace"


@pytest.mark.asyncio
async def test_upsert_and_get_strategy(migrated_pool: asyncpg.Pool, ws_id: UUID) -> None:
    await upsert_strategy(migrated_pool, ws_id, "LESSONS.md", "append", "ui")
    result = await get_strategy(migrated_pool, ws_id, "LESSONS.md")
    assert result == "append"


@pytest.mark.asyncio
async def test_upsert_idempotent(migrated_pool: asyncpg.Pool, ws_id: UUID) -> None:
    await upsert_strategy(migrated_pool, ws_id, "LESSONS.md", "append", "ui")
    await upsert_strategy(migrated_pool, ws_id, "LESSONS.md", "replace", "strategy_file")
    result = await get_strategy(migrated_pool, ws_id, "LESSONS.md")
    assert result == "replace"


@pytest.mark.asyncio
async def test_upsert_batch(migrated_pool: asyncpg.Pool, ws_id: UUID) -> None:
    strategies = {"LESSONS.md": "append", "docs/CHANGELOG.md": "append"}
    await upsert_strategies_batch(migrated_pool, ws_id, strategies)  # type: ignore[arg-type]
    assert await get_strategy(migrated_pool, ws_id, "LESSONS.md") == "append"
    assert await get_strategy(migrated_pool, ws_id, "docs/CHANGELOG.md") == "append"
    assert await get_strategy(migrated_pool, ws_id, "other.md") == "replace"


@pytest.mark.asyncio
async def test_cascade_delete(migrated_pool: asyncpg.Pool, ws_id: UUID) -> None:
    await upsert_strategy(migrated_pool, ws_id, "LESSONS.md", "append", "ui")
    async with migrated_pool.acquire() as conn:
        await conn.execute("DELETE FROM workspaces WHERE id=$1", ws_id)
    row = await migrated_pool.fetchrow(
        "SELECT * FROM path_strategies WHERE workspace_id=$1", ws_id
    )
    assert row is None
```

- [ ] **Vérifier que le test échoue**

```bash
cd backend && uv run pytest tests/integration/test_path_strategies.py -v
```

Résultat attendu : `ImportError: cannot import name 'get_strategy'`

- [ ] **Implémenter `db/path_strategies.py`**

```python
# backend/src/rag/db/path_strategies.py
from __future__ import annotations

from typing import Literal
from uuid import UUID

import asyncpg
import structlog

log = structlog.get_logger(__name__)


async def get_strategy(
    pool: asyncpg.Pool,
    workspace_id: UUID,
    path: str,
) -> Literal["replace", "append"]:
    row = await pool.fetchrow(
        "SELECT strategy FROM path_strategies WHERE workspace_id=$1 AND path=$2",
        workspace_id,
        path,
    )
    if row is None:
        return "replace"
    return row["strategy"]  # type: ignore[return-value]


async def upsert_strategy(
    pool: asyncpg.Pool,
    workspace_id: UUID,
    path: str,
    strategy: Literal["replace", "append"],
    updated_by: Literal["ui", "strategy_file"] = "ui",
) -> None:
    await pool.execute(
        """
        INSERT INTO path_strategies (workspace_id, path, strategy, updated_by, updated_at)
        VALUES ($1, $2, $3, $4, now())
        ON CONFLICT (workspace_id, path) DO UPDATE
        SET strategy=EXCLUDED.strategy, updated_by=EXCLUDED.updated_by, updated_at=now()
        """,
        workspace_id,
        path,
        strategy,
        updated_by,
    )
    log.debug(
        "path_strategies.upserted",
        workspace_id=str(workspace_id),
        path=path,
        strategy=strategy,
        updated_by=updated_by,
    )


async def upsert_strategies_batch(
    pool: asyncpg.Pool,
    workspace_id: UUID,
    strategies: dict[str, Literal["replace", "append"]],
    updated_by: Literal["ui", "strategy_file"] = "strategy_file",
) -> None:
    if not strategies:
        return
    records = [
        (workspace_id, path, strategy, updated_by)
        for path, strategy in strategies.items()
    ]
    async with pool.acquire() as conn, conn.transaction():
        await conn.executemany(
            """
            INSERT INTO path_strategies (workspace_id, path, strategy, updated_by, updated_at)
            VALUES ($1, $2, $3, $4, now())
            ON CONFLICT (workspace_id, path) DO UPDATE
            SET strategy=EXCLUDED.strategy, updated_by=EXCLUDED.updated_by, updated_at=now()
            """,
            records,
        )
    log.info(
        "path_strategies.batch_upserted",
        workspace_id=str(workspace_id),
        count=len(strategies),
    )


async def get_all_for_workspace(
    pool: asyncpg.Pool,
    workspace_id: UUID,
) -> dict[str, dict]:
    rows = await pool.fetch(
        """
        SELECT path, strategy, updated_by, updated_at
        FROM path_strategies
        WHERE workspace_id=$1
        """,
        workspace_id,
    )
    return {r["path"]: dict(r) for r in rows}
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/integration/test_path_strategies.py -v
```

Résultat attendu : `5 passed`

- [ ] **Commit**

```bash
git add backend/src/rag/db/path_strategies.py backend/tests/integration/test_path_strategies.py
git commit -m "feat(db): path_strategies CRUD — get_strategy, upsert, batch, get_all"
```

---

## Task 3 — Modifier `upsert_chunks` pour le paramètre `strategy`

**Files:**
- Modify: `backend/src/rag/db/workspace_embeddings.py`
- Create: `backend/tests/integration/test_upsert_chunks_strategy.py`

- [ ] **Écrire les tests (rouge)**

```python
# backend/tests/integration/test_upsert_chunks_strategy.py
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio
from pgvector.asyncpg import register_vector

from rag.db.workspace_embeddings import upsert_chunks
from rag.indexer.chunking import Chunk


@pytest_asyncio.fixture
async def ws_pool(pg_container: str) -> AsyncIterator[asyncpg.Pool]:
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    dbname = f"rag_test_strat_{uuid.uuid4().hex[:10]}"
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        await admin.close()

    ws_dsn = pg_container.rsplit("/", 1)[0] + f"/{dbname}"
    setup = await asyncpg.connect(ws_dsn)
    try:
        await setup.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await setup.execute(
            """
            CREATE TABLE embeddings (
                id           SERIAL PRIMARY KEY,
                path         TEXT NOT NULL,
                chunk_index  INT  NOT NULL,
                content      TEXT NOT NULL,
                embedding    vector(4) NOT NULL,
                metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
                indexed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (path, chunk_index)
            )
            """
        )
    finally:
        await setup.close()

    pool = await asyncpg.create_pool(
        ws_dsn, min_size=1, max_size=2,
        init=register_vector,
    )
    try:
        yield pool
    finally:
        await pool.close()
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        finally:
            await admin.close()


def _chunks(texts: list[str]) -> tuple[list[Chunk], list[list[float]]]:
    chunks = [Chunk(content=t, metadata={}) for t in texts]
    embeddings = [[0.1, 0.2, 0.3, 0.4]] * len(texts)
    return chunks, embeddings


@pytest.mark.asyncio
async def test_replace_strategy_overwrites(ws_pool: asyncpg.Pool) -> None:
    chunks_v1, embs_v1 = _chunks(["version 1"])
    await upsert_chunks(ws_pool, path="LESSONS.md", chunks=chunks_v1, embeddings=embs_v1, strategy="replace")

    chunks_v2, embs_v2 = _chunks(["version 2"])
    await upsert_chunks(ws_pool, path="LESSONS.md", chunks=chunks_v2, embeddings=embs_v2, strategy="replace")

    async with ws_pool.acquire() as conn:
        rows = await conn.fetch("SELECT content FROM embeddings WHERE path='LESSONS.md'")
    assert len(rows) == 1
    assert rows[0]["content"] == "version 2"


@pytest.mark.asyncio
async def test_append_strategy_accumulates(ws_pool: asyncpg.Pool) -> None:
    chunks_v1, embs_v1 = _chunks(["version 1"])
    await upsert_chunks(ws_pool, path="LESSONS.md", chunks=chunks_v1, embeddings=embs_v1, strategy="append")

    chunks_v2, embs_v2 = _chunks(["version 2"])
    await upsert_chunks(ws_pool, path="LESSONS.md", chunks=chunks_v2, embeddings=embs_v2, strategy="append")

    async with ws_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT content FROM embeddings WHERE path='LESSONS.md' ORDER BY id"
        )
    contents = [r["content"] for r in rows]
    assert "version 1" in contents
    assert "version 2" in contents
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_append_two_batches_distinct_indexed_at(ws_pool: asyncpg.Pool) -> None:
    """Deux batches append → deux indexed_at distincts (versions séparées)."""
    import asyncio
    chunks1, embs1 = _chunks(["lesson A"])
    await upsert_chunks(ws_pool, path="LESSONS.md", chunks=chunks1, embeddings=embs1, strategy="append")
    await asyncio.sleep(0.01)  # garantit un now() différent
    chunks2, embs2 = _chunks(["lesson B"])
    await upsert_chunks(ws_pool, path="LESSONS.md", chunks=chunks2, embeddings=embs2, strategy="append")

    async with ws_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT indexed_at FROM embeddings WHERE path='LESSONS.md'"
        )
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_default_strategy_is_replace(ws_pool: asyncpg.Pool) -> None:
    chunks1, embs1 = _chunks(["v1"])
    await upsert_chunks(ws_pool, path="f.md", chunks=chunks1, embeddings=embs1)  # sans strategy
    chunks2, embs2 = _chunks(["v2"])
    await upsert_chunks(ws_pool, path="f.md", chunks=chunks2, embeddings=embs2)

    async with ws_pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM embeddings WHERE path='f.md'")
    assert count == 1
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/integration/test_upsert_chunks_strategy.py -v
```

Résultat attendu : `TypeError: upsert_chunks() got an unexpected keyword argument 'strategy'`

- [ ] **Modifier `upsert_chunks` dans `workspace_embeddings.py`**

Remplacer la signature et le corps de `upsert_chunks` :

```python
# backend/src/rag/db/workspace_embeddings.py
from __future__ import annotations

import json
from typing import Literal

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
    strategy: Literal["replace", "append"] = "replace",
) -> int:
    """Indexe les chunks d'un path selon la stratégie donnée.

    replace (défaut) : DELETE WHERE path puis INSERT — comportement d'origine.
    append           : INSERT uniquement, pas de DELETE. Les anciennes versions
                       sont conservées et distinguées par leur indexed_at.

    Pré-condition : len(chunks) == len(embeddings), sinon ValueError.
    Retourne le nombre de chunks insérés.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) must have the same length"
        )
    if not chunks:
        if strategy == "replace":
            await delete_chunks_for_path(workspace_pool, path)
        return 0

    async with workspace_pool.acquire() as conn, conn.transaction():
        await register_vector(conn)
        if strategy == "replace":
            await conn.execute("DELETE FROM embeddings WHERE path=$1", path)
        records = [
            (path, idx, chunk.content, embedding, json.dumps(dict(chunk.metadata)))
            for idx, (chunk, embedding) in enumerate(
                zip(chunks, embeddings, strict=True),
            )
        ]
        await conn.executemany(
            "INSERT INTO embeddings (path, chunk_index, content, embedding, metadata) "
            "VALUES ($1, $2, $3, $4, $5::jsonb)",
            records,
        )

    log.info(
        "workspace_embeddings.upserted",
        path=path,
        chunks=len(chunks),
        strategy=strategy,
    )
    return len(chunks)


async def delete_chunks_for_path(
    workspace_pool: asyncpg.Pool,
    path: str,
) -> int:
    """DELETE FROM embeddings WHERE path=$1. Retourne nombre supprimé."""
    async with workspace_pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM embeddings WHERE path=$1",
            path,
        )
    count = int(result.split()[-1])
    if count > 0:
        log.info(
            "workspace_embeddings.deleted",
            path=path,
            count=count,
        )
    return count


async def delete_path(workspace_pool: asyncpg.Pool, path: str) -> None:
    """Alias sémantique de delete_chunks_for_path utilisé par RealIndexer."""
    await delete_chunks_for_path(workspace_pool, path)
```

> **Note :** En mode `append`, l'UNIQUE constraint `(path, chunk_index)` pose problème : deux batches append auraient le même `chunk_index=0`. La solution : en mode `append`, on insère avec un `chunk_index` calculé à partir du MAX existant pour ce path. Voir ajustement ci-dessous :

```python
# Remplacement du bloc INSERT dans upsert_chunks pour append
        if strategy == "append":
            # Calcule l'offset pour éviter collision sur (path, chunk_index)
            max_idx = await conn.fetchval(
                "SELECT COALESCE(MAX(chunk_index), -1) FROM embeddings WHERE path=$1",
                path,
            ) or -1
            records = [
                (path, max_idx + 1 + idx, chunk.content, embedding, json.dumps(dict(chunk.metadata)))
                for idx, (chunk, embedding) in enumerate(
                    zip(chunks, embeddings, strict=True),
                )
            ]
        else:
            records = [
                (path, idx, chunk.content, embedding, json.dumps(dict(chunk.metadata)))
                for idx, (chunk, embedding) in enumerate(
                    zip(chunks, embeddings, strict=True),
                )
            ]
```

Le code final complet de `upsert_chunks` avec ce correctif :

```python
async def upsert_chunks(
    workspace_pool: asyncpg.Pool,
    *,
    path: str,
    chunks: list[Chunk],
    embeddings: list[list[float]],
    strategy: Literal["replace", "append"] = "replace",
) -> int:
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) must have the same length"
        )
    if not chunks:
        if strategy == "replace":
            await delete_chunks_for_path(workspace_pool, path)
        return 0

    async with workspace_pool.acquire() as conn, conn.transaction():
        await register_vector(conn)
        if strategy == "replace":
            await conn.execute("DELETE FROM embeddings WHERE path=$1", path)
            records = [
                (path, idx, chunk.content, embedding, json.dumps(dict(chunk.metadata)))
                for idx, (chunk, embedding) in enumerate(
                    zip(chunks, embeddings, strict=True),
                )
            ]
        else:
            max_idx = await conn.fetchval(
                "SELECT COALESCE(MAX(chunk_index), -1) FROM embeddings WHERE path=$1",
                path,
            ) or -1
            records = [
                (path, max_idx + 1 + idx, chunk.content, embedding, json.dumps(dict(chunk.metadata)))
                for idx, (chunk, embedding) in enumerate(
                    zip(chunks, embeddings, strict=True),
                )
            ]
        await conn.executemany(
            "INSERT INTO embeddings (path, chunk_index, content, embedding, metadata) "
            "VALUES ($1, $2, $3, $4, $5::jsonb)",
            records,
        )

    log.info(
        "workspace_embeddings.upserted",
        path=path,
        chunks=len(chunks),
        strategy=strategy,
    )
    return len(chunks)
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/integration/test_upsert_chunks_strategy.py -v
```

Résultat attendu : `4 passed`

- [ ] **Vérifier que les tests existants restent verts**

```bash
cd backend && uv run pytest tests/integration/test_workspace_embeddings.py -v
```

Résultat attendu : tous les tests passent (pas de régression).

- [ ] **Commit**

```bash
git add backend/src/rag/db/workspace_embeddings.py backend/tests/integration/test_upsert_chunks_strategy.py
git commit -m "feat(db): upsert_chunks — paramètre strategy replace/append"
```

---

## Task 4 — DB layer `index_keys` (requêtes workspace DB)

**Files:**
- Create: `backend/src/rag/db/index_keys.py`

- [ ] **Créer le module**

```python
# backend/src/rag/db/index_keys.py
from __future__ import annotations

import json
from typing import Any

import asyncpg
import structlog
from pgvector.asyncpg import register_vector

log = structlog.get_logger(__name__)


async def list_paths_aggregate(
    workspace_pool: asyncpg.Pool,
    paths: list[str],
) -> dict[str, dict[str, Any]]:
    """Agrégats chunk_count / version_count / last_indexed_at par path.

    Ne requête que les paths fournis (déjà filtrés depuis indexed_documents).
    Paths absents de embeddings → non présents dans le résultat.
    """
    if not paths:
        return {}
    async with workspace_pool.acquire() as conn:
        await register_vector(conn)
        rows = await conn.fetch(
            """
            SELECT path,
                   COUNT(*)::int                    AS chunk_count,
                   COUNT(DISTINCT indexed_at)::int  AS version_count,
                   MAX(indexed_at)                  AS last_indexed_at
            FROM embeddings
            WHERE path = ANY($1::text[])
            GROUP BY path
            """,
            paths,
        )
    return {
        r["path"]: {
            "chunk_count": r["chunk_count"],
            "version_count": r["version_count"],
            "last_indexed_at": r["last_indexed_at"],
        }
        for r in rows
    }


async def get_path_chunks(
    workspace_pool: asyncpg.Pool,
    path: str,
) -> list[dict[str, Any]]:
    """Chunks d'un path triés par indexed_at DESC puis chunk_index ASC."""
    async with workspace_pool.acquire() as conn:
        await register_vector(conn)
        rows = await conn.fetch(
            """
            SELECT chunk_index, content, metadata, indexed_at
            FROM embeddings
            WHERE path = $1
            ORDER BY indexed_at DESC, chunk_index ASC
            """,
            path,
        )
    result = []
    for r in rows:
        metadata = r["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        result.append({
            "chunk_index": r["chunk_index"],
            "content": r["content"],
            "metadata": metadata,
            "indexed_at": r["indexed_at"],
        })
    return result
```

- [ ] **Vérifier lint**

```bash
cd backend && uv run ruff check src/rag/db/index_keys.py
```

Résultat attendu : pas d'erreur

- [ ] **Commit**

```bash
git add backend/src/rag/db/index_keys.py
git commit -m "feat(db): index_keys — list_paths_aggregate et get_path_chunks"
```

---

## Task 5 — Schémas Pydantic `index_keys`

**Files:**
- Create: `backend/src/rag/schemas/index_keys.py`

- [ ] **Créer le module**

```python
# backend/src/rag/schemas/index_keys.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class PathStrategyEntry(BaseModel):
    path: str
    strategy: Literal["replace", "append"]
    updated_by: Literal["ui", "strategy_file"]
    chunk_count: int
    version_count: int
    last_indexed_at: datetime | None


class IndexKeysResponse(BaseModel):
    paths: list[PathStrategyEntry]
    total: int


class ChunkEntry(BaseModel):
    chunk_index: int
    content: str
    metadata: dict[str, Any]
    indexed_at: datetime


class VersionGroup(BaseModel):
    indexed_at: datetime
    chunks: list[ChunkEntry]


class PathDetailResponse(BaseModel):
    path: str
    strategy: Literal["replace", "append"]
    updated_by: Literal["ui", "strategy_file"]
    versions: list[VersionGroup]


class StrategyPatchRequest(BaseModel):
    strategy: Literal["replace", "append"]
```

- [ ] **Vérifier lint**

```bash
cd backend && uv run ruff check src/rag/schemas/index_keys.py
```

Résultat attendu : pas d'erreur

- [ ] **Commit**

```bash
git add backend/src/rag/schemas/index_keys.py
git commit -m "feat(schemas): index_keys — PathStrategyEntry, IndexKeysResponse, PathDetailResponse"
```

---

## Task 6 — Router API `admin_index_keys`

**Files:**
- Create: `backend/src/rag/api/admin_index_keys.py`
- Modify: `backend/src/rag/main.py`

- [ ] **Créer le router**

```python
# backend/src/rag/api/admin_index_keys.py
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.db.index_keys import get_path_chunks, list_paths_aggregate
from rag.db.path_strategies import get_all_for_workspace, upsert_strategy
from rag.db.pool import WorkspacePoolRegistry
from rag.schemas.index_keys import (
    ChunkEntry,
    IndexKeysResponse,
    PathDetailResponse,
    PathStrategyEntry,
    StrategyPatchRequest,
    VersionGroup,
)


def build_index_keys_router() -> APIRouter:
    router = APIRouter(
        tags=["admin"],
        dependencies=[Depends(require_master_key_or_authenticated_admin)],
    )

    async def _workspace_context(
        config_pool: asyncpg.Pool,
        name: str,
    ) -> tuple[UUID, str]:
        """Retourne (workspace_id, rag_cnx) ou lève 404."""
        row = await config_pool.fetchrow(
            "SELECT id, rag_cnx FROM workspaces WHERE name=$1", name
        )
        if row is None:
            raise HTTPException(status_code=404, detail="workspace_not_found")
        return row["id"], row["rag_cnx"]

    async def _ws_pool(
        request: Request,
        workspace_name: str,
        rag_cnx: str,
    ) -> asyncpg.Pool:
        # Vérifier dans main.py la bonne clé app.state : chercher WorkspacePoolRegistry
        # dans le lifespan. Pattern habituel : request.app.state.pool_registry
        registry: WorkspacePoolRegistry = request.app.state.pool_registry
        return await registry.get_workspace_pool(workspace_name, rag_cnx)

    @router.get("/workspaces/{name}/index-keys", response_model=IndexKeysResponse)
    async def get_index_keys(name: str, request: Request) -> IndexKeysResponse:
        config_pool: asyncpg.Pool = request.app.state.pools.config_pool
        ws_id, rag_cnx = await _workspace_context(config_pool, name)

        path_rows = await config_pool.fetch(
            "SELECT path FROM indexed_documents WHERE workspace_id=$1 ORDER BY path",
            ws_id,
        )
        paths = [r["path"] for r in path_rows]
        strategies = await get_all_for_workspace(config_pool, ws_id)
        ws_pool = await _ws_pool(request, name, rag_cnx)
        agg = await list_paths_aggregate(ws_pool, paths)

        entries = [
            PathStrategyEntry(
                path=p,
                strategy=strategies[p]["strategy"] if p in strategies else "replace",
                updated_by=strategies[p]["updated_by"] if p in strategies else "ui",
                chunk_count=agg.get(p, {}).get("chunk_count", 0),
                version_count=agg.get(p, {}).get("version_count", 0),
                last_indexed_at=agg.get(p, {}).get("last_indexed_at"),
            )
            for p in paths
        ]
        return IndexKeysResponse(paths=entries, total=len(entries))

    @router.get(
        "/workspaces/{name}/index-keys/{path:path}",
        response_model=PathDetailResponse,
    )
    async def get_index_key_detail(
        name: str, path: str, request: Request
    ) -> PathDetailResponse:
        config_pool: asyncpg.Pool = request.app.state.pools.config_pool
        ws_id, rag_cnx = await _workspace_context(config_pool, name)

        strategies = await get_all_for_workspace(config_pool, ws_id)
        strat = strategies.get(path)
        ws_pool = await _ws_pool(request, name, rag_cnx)
        chunks_raw = await get_path_chunks(ws_pool, path)

        by_version: dict[datetime, list[ChunkEntry]] = defaultdict(list)
        for c in chunks_raw:
            by_version[c["indexed_at"]].append(
                ChunkEntry(
                    chunk_index=c["chunk_index"],
                    content=c["content"],
                    metadata=c["metadata"],
                    indexed_at=c["indexed_at"],
                )
            )

        versions = [
            VersionGroup(indexed_at=ts, chunks=chunks_list)
            for ts, chunks_list in sorted(by_version.items(), reverse=True)
        ]
        return PathDetailResponse(
            path=path,
            strategy=strat["strategy"] if strat else "replace",
            updated_by=strat["updated_by"] if strat else "ui",
            versions=versions,
        )

    @router.patch(
        "/workspaces/{name}/index-keys/{path:path}/strategy",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def patch_index_key_strategy(
        name: str,
        path: str,
        payload: StrategyPatchRequest,
        request: Request,
    ) -> Response:
        config_pool: asyncpg.Pool = request.app.state.pools.config_pool
        ws_id, _ = await _workspace_context(config_pool, name)
        await upsert_strategy(config_pool, ws_id, path, payload.strategy, "ui")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
```

- [ ] **Câbler le router dans `main.py`**

Ajouter l'import et l'include. Dans `backend/src/rag/main.py`, après la ligne qui importe `build_admin_router` :

```python
from rag.api.admin_index_keys import build_index_keys_router
```

Dans la fonction `create_app` ou l'endroit où les routers sont inclus, ajouter :

```python
app.include_router(build_index_keys_router(), prefix="/api/admin")
```

- [ ] **Vérifier lint**

```bash
cd backend && uv run ruff check src/rag/api/admin_index_keys.py src/rag/main.py
```

Résultat attendu : pas d'erreur

- [ ] **Démarrer le backend et vérifier que les routes apparaissent**

```bash
cd backend && uv run uvicorn rag.main:app --reload
```

Ouvrir `http://localhost:8000/docs` et vérifier la présence de :
- `GET /api/admin/workspaces/{name}/index-keys`
- `GET /api/admin/workspaces/{name}/index-keys/{path}`
- `PATCH /api/admin/workspaces/{name}/index-keys/{path}/strategy`

- [ ] **Commit**

```bash
git add backend/src/rag/api/admin_index_keys.py backend/src/rag/main.py
git commit -m "feat(api): router admin_index_keys — GET list, GET detail, PATCH strategy"
```

---

## Task 7 — Tests API `admin_index_keys`

**Files:**
- Create: `backend/tests/api/test_admin_index_keys.py`

- [ ] **Écrire les tests**

```python
# backend/tests/api/test_admin_index_keys.py
from __future__ import annotations

import os

import asyncpg
import pytest
from fastapi.testclient import TestClient


def _create_ws(client: TestClient, headers: dict[str, str], name: str) -> dict:
    r = client.post(
        "/api/admin/workspaces",
        headers=headers,
        json={
            "name": name,
            "api_key_vault": "rag",
            "indexer": {
                "provider": "ollama",
                "model": "mxbai-embed-large",
                "api_key_ref": None,
                "base_url": "http://stub:11434",
            },
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _insert_doc(workspace_name: str, path: str = "LESSONS.md") -> None:
    import asyncio

    async def _go() -> None:
        conn = await asyncpg.connect(os.environ["DATABASE_URL"])
        try:
            ws_id = await conn.fetchval(
                "SELECT id FROM workspaces WHERE name=$1", workspace_name
            )
            await conn.execute(
                "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
                "VALUES ($1, $2, 'sha256:0', 'ollama/mxbai-embed-large')",
                ws_id,
                path,
            )
        finally:
            await conn.close()

    asyncio.get_event_loop().run_until_complete(_go())


def test_get_index_keys_empty(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    _create_ws(admin_client, admin_headers, "ws_ik_empty")
    r = admin_client.get("/api/admin/workspaces/ws_ik_empty/index-keys", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["paths"] == []


def test_get_index_keys_lists_paths(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    _create_ws(admin_client, admin_headers, "ws_ik_paths")
    _insert_doc("ws_ik_paths", "LESSONS.md")
    _insert_doc("ws_ik_paths", "docs/api.md")

    r = admin_client.get("/api/admin/workspaces/ws_ik_paths/index-keys", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    paths = [e["path"] for e in body["paths"]]
    assert "LESSONS.md" in paths
    assert "docs/api.md" in paths


def test_get_index_keys_default_strategy_replace(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    _create_ws(admin_client, admin_headers, "ws_ik_defstrat")
    _insert_doc("ws_ik_defstrat", "README.md")

    r = admin_client.get(
        "/api/admin/workspaces/ws_ik_defstrat/index-keys", headers=admin_headers
    )
    assert r.status_code == 200
    entry = r.json()["paths"][0]
    assert entry["strategy"] == "replace"
    assert entry["updated_by"] == "ui"


def test_patch_strategy_and_read_back(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    _create_ws(admin_client, admin_headers, "ws_ik_patch")
    _insert_doc("ws_ik_patch", "LESSONS.md")

    r = admin_client.patch(
        "/api/admin/workspaces/ws_ik_patch/index-keys/LESSONS.md/strategy",
        headers=admin_headers,
        json={"strategy": "append"},
    )
    assert r.status_code == 204

    r2 = admin_client.get(
        "/api/admin/workspaces/ws_ik_patch/index-keys", headers=admin_headers
    )
    entry = next(e for e in r2.json()["paths"] if e["path"] == "LESSONS.md")
    assert entry["strategy"] == "append"
    assert entry["updated_by"] == "ui"


def test_patch_strategy_idempotent(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    _create_ws(admin_client, admin_headers, "ws_ik_idem")
    _insert_doc("ws_ik_idem", "LESSONS.md")

    for _ in range(2):
        r = admin_client.patch(
            "/api/admin/workspaces/ws_ik_idem/index-keys/LESSONS.md/strategy",
            headers=admin_headers,
            json={"strategy": "append"},
        )
        assert r.status_code == 204


def test_get_index_keys_404_unknown_workspace(
    admin_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    r = admin_client.get(
        "/api/admin/workspaces/nonexistent/index-keys", headers=admin_headers
    )
    assert r.status_code == 404


def test_patch_strategy_422_invalid_value(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    _create_ws(admin_client, admin_headers, "ws_ik_422")
    r = admin_client.patch(
        "/api/admin/workspaces/ws_ik_422/index-keys/LESSONS.md/strategy",
        headers=admin_headers,
        json={"strategy": "invalid"},
    )
    assert r.status_code == 422
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/api/test_admin_index_keys.py -v
```

Résultat attendu : `7 passed`

- [ ] **Commit**

```bash
git add backend/tests/api/test_admin_index_keys.py
git commit -m "test(api): couverture admin_index_keys — GET list/detail, PATCH, 404, 422"
```

---

## Task 8 — RealIndexer lit la stratégie avant `upsert_chunks`

**Files:**
- Modify: `backend/src/rag/indexer/real.py`

- [ ] **Modifier `index_file` dans `real.py`**

Ajouter l'import en tête de fichier :

```python
from rag.db.path_strategies import get_strategy
```

Dans la méthode `index_file`, après la ligne `ws_pool = await ...` et avant l'appel `await upsert_chunks(...)`, ajouter :

```python
        strategy = await get_strategy(self._config_pool, workspace_id, path)
```

Puis passer `strategy=strategy` à `upsert_chunks` :

```python
        await upsert_chunks(
            ws_pool,
            path=path,
            chunks=chunks,
            embeddings=embeddings,
            strategy=strategy,
        )
```

Le bloc complet autour de ces lignes dans `index_file` (lignes ~133-143) devient :

```python
        ws_pool = await self._pool_registry.get_workspace_pool(
            ctx["workspace_name"],
            ctx["rag_cnx"],
        )
        strategy = await get_strategy(self._config_pool, workspace_id, path)
        await upsert_chunks(
            ws_pool,
            path=path,
            chunks=chunks,
            embeddings=embeddings,
            strategy=strategy,
        )
```

- [ ] **Vérifier lint**

```bash
cd backend && uv run ruff check src/rag/indexer/real.py
```

Résultat attendu : pas d'erreur

- [ ] **Vérifier que les tests existants du real indexer passent**

```bash
cd backend && uv run pytest tests/ -k "real_indexer" -v
```

Résultat attendu : tous les tests passent

- [ ] **Commit**

```bash
git add backend/src/rag/indexer/real.py
git commit -m "feat(indexer): RealIndexer lit la stratégie par path avant upsert_chunks"
```

---

## Task 9 — Module `strategy_config` (lecture `.rag/strategy.yml`)

**Files:**
- Create: `backend/src/rag/sync/strategy_config.py`
- Create: `backend/tests/unit/test_parse_strategy_file.py`

- [ ] **Écrire les tests (rouge)**

```python
# backend/tests/unit/test_parse_strategy_file.py
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from rag.sync.strategy_config import parse_strategy_file


def test_returns_empty_dict_when_file_absent(tmp_path: Path) -> None:
    result = parse_strategy_file(tmp_path)
    assert result == {}


def test_parses_valid_yaml(tmp_path: Path) -> None:
    rag_dir = tmp_path / ".rag"
    rag_dir.mkdir()
    (rag_dir / "strategy.yml").write_text(
        textwrap.dedent("""\
            strategies:
              LESSONS.md: append
              docs/CHANGELOG.md: append
        """)
    )
    result = parse_strategy_file(tmp_path)
    assert result == {"LESSONS.md": "append", "docs/CHANGELOG.md": "append"}


def test_ignores_unknown_strategy_values(tmp_path: Path) -> None:
    rag_dir = tmp_path / ".rag"
    rag_dir.mkdir()
    (rag_dir / "strategy.yml").write_text(
        textwrap.dedent("""\
            strategies:
              LESSONS.md: append
              README.md: invalid_value
              notes.md: replace
        """)
    )
    result = parse_strategy_file(tmp_path)
    assert "README.md" not in result
    assert result["LESSONS.md"] == "append"
    assert result["notes.md"] == "replace"


def test_returns_empty_dict_when_strategies_key_absent(tmp_path: Path) -> None:
    rag_dir = tmp_path / ".rag"
    rag_dir.mkdir()
    (rag_dir / "strategy.yml").write_text("other_key: value\n")
    result = parse_strategy_file(tmp_path)
    assert result == {}


def test_returns_empty_dict_on_invalid_yaml(tmp_path: Path) -> None:
    rag_dir = tmp_path / ".rag"
    rag_dir.mkdir()
    (rag_dir / "strategy.yml").write_text(":\n  - bad: yaml: content\n")
    result = parse_strategy_file(tmp_path)
    assert result == {}
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_parse_strategy_file.py -v
```

Résultat attendu : `ModuleNotFoundError` ou `ImportError`

- [ ] **Implémenter `sync/strategy_config.py`**

```python
# backend/src/rag/sync/strategy_config.py
from __future__ import annotations

from pathlib import Path
from typing import Literal

import structlog
import yaml

log = structlog.get_logger(__name__)

_VALID_STRATEGIES = frozenset({"replace", "append"})
_STRATEGY_FILE = Path(".rag") / "strategy.yml"


def parse_strategy_file(
    repo_path: Path,
) -> dict[str, Literal["replace", "append"]]:
    """Lit `.rag/strategy.yml` dans `repo_path` et retourne un dict path → strategy.

    Retourne un dict vide si le fichier est absent, malformé ou ne contient
    pas de clé `strategies`.
    Les valeurs inconnues (ni 'replace' ni 'append') sont silencieusement ignorées.
    """
    yml_path = repo_path / _STRATEGY_FILE
    if not yml_path.exists():
        return {}

    try:
        raw = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        log.warning("strategy_config.parse_error", path=str(yml_path), error=str(exc))
        return {}

    if not isinstance(raw, dict):
        return {}

    strategies_raw = raw.get("strategies")
    if not isinstance(strategies_raw, dict):
        return {}

    result: dict[str, Literal["replace", "append"]] = {}
    for path, value in strategies_raw.items():
        if value in _VALID_STRATEGIES:
            result[str(path)] = value  # type: ignore[assignment]
        else:
            log.warning(
                "strategy_config.unknown_strategy",
                path=str(path),
                value=value,
            )
    return result
```

- [ ] **Vérifier que PyYAML est dans les dépendances**

```bash
cd backend && uv run python -c "import yaml; print('ok')"
```

Si `ModuleNotFoundError` : `uv add pyyaml` et recommiter `pyproject.toml`.

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_parse_strategy_file.py -v
```

Résultat attendu : `5 passed`

- [ ] **Commit**

```bash
git add backend/src/rag/sync/strategy_config.py backend/tests/unit/test_parse_strategy_file.py
git commit -m "feat(sync): strategy_config — parse_strategy_file lit .rag/strategy.yml"
```

---

## Task 10 — Câbler `strategy_config` dans l'exécuteur git

**Files:**
- Modify: `backend/src/rag/sync/executor.py`

- [ ] **Ajouter l'import dans `executor.py`**

En tête de `executor.py`, ajouter :

```python
from rag.db.path_strategies import upsert_strategies_batch
from rag.sync.strategy_config import parse_strategy_file
```

- [ ] **Appeler `parse_strategy_file` et `upsert_strategies_batch` dans `_execute_git_job`**

Dans `_execute_git_job`, après la ligne `changes = filter_glob(...)` (ligne ~489) et avant la boucle `for path in changes.added + changes.modified:`, insérer :

```python
    # Lit .rag/strategy.yml et UPSERT les stratégies en base (le fichier prime sur l'IHM)
    file_strategies = parse_strategy_file(dest)
    if file_strategies:
        await upsert_strategies_batch(config_pool, job.workspace_id, file_strategies)
        _log("info", f"Stratégies depuis .rag/strategy.yml : {len(file_strategies)} path(s).")
```

- [ ] **Vérifier lint**

```bash
cd backend && uv run ruff check src/rag/sync/executor.py
```

Résultat attendu : pas d'erreur

- [ ] **Vérifier que les tests existants de l'executor passent**

```bash
cd backend && uv run pytest tests/ -k "executor" -v
```

Résultat attendu : tous les tests passent

- [ ] **Commit**

```bash
git add backend/src/rag/sync/executor.py
git commit -m "feat(sync): executor — lit .rag/strategy.yml après git pull et UPSERT strategies"
```

---

## Task 11 — Frontend : types et client API

**Files:**
- Modify: `frontend/src/lib/workspaces.types.ts`
- Modify: `frontend/src/lib/workspaces.ts`

- [ ] **Ajouter les types dans `workspaces.types.ts`**

À la fin du fichier, ajouter :

```typescript
export type IndexKeyStrategy = "replace" | "append";
export type IndexKeyUpdatedBy = "ui" | "strategy_file";

export type PathStrategyEntry = {
  path: string;
  strategy: IndexKeyStrategy;
  updated_by: IndexKeyUpdatedBy;
  chunk_count: number;
  version_count: number;
  last_indexed_at: string | null;
};

export type IndexKeysResponse = {
  paths: PathStrategyEntry[];
  total: number;
};

export type ChunkEntry = {
  chunk_index: number;
  content: string;
  metadata: Record<string, unknown>;
  indexed_at: string;
};

export type VersionGroup = {
  indexed_at: string;
  chunks: ChunkEntry[];
};

export type PathDetailResponse = {
  path: string;
  strategy: IndexKeyStrategy;
  updated_by: IndexKeyUpdatedBy;
  versions: VersionGroup[];
};

export type StrategyPatchRequest = {
  strategy: IndexKeyStrategy;
};
```

- [ ] **Ajouter les appels API dans `workspaces.ts`**

Ajouter les imports manquants en tête :

```typescript
import type {
  // ... imports existants ...
  IndexKeysResponse,
  PathDetailResponse,
  StrategyPatchRequest,
} from "@/lib/workspaces.types";
```

Puis dans l'objet `workspacesApi`, ajouter :

```typescript
  listIndexKeys: (name: string) =>
    api.get<IndexKeysResponse>(`${BASE}/${name}/index-keys`),

  getIndexKeyDetail: (name: string, path: string) =>
    api.get<PathDetailResponse>(`${BASE}/${name}/index-keys/${path}`),

  patchIndexKeyStrategy: (name: string, path: string, payload: StrategyPatchRequest) =>
    api.patch<void>(`${BASE}/${name}/index-keys/${encodeURIComponent(path)}/strategy`, payload),
```

- [ ] **Vérifier TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

Résultat attendu : pas d'erreur

- [ ] **Commit**

```bash
git add frontend/src/lib/workspaces.types.ts frontend/src/lib/workspaces.ts
git commit -m "feat(frontend): types et API client index-keys"
```

---

## Task 12 — Frontend : hooks React Query

**Files:**
- Create: `frontend/src/hooks/useIndexKeys.ts`

- [ ] **Créer le fichier**

```typescript
// frontend/src/hooks/useIndexKeys.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { workspacesApi } from "@/lib/workspaces";
import type { IndexKeyStrategy } from "@/lib/workspaces.types";

export function useIndexKeys(workspaceName: string, enabled: boolean) {
  return useQuery({
    queryKey: ["workspace", workspaceName, "index-keys"],
    queryFn: () => workspacesApi.listIndexKeys(workspaceName),
    enabled,
  });
}

export function useIndexKeyDetail(
  workspaceName: string,
  path: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["workspace", workspaceName, "index-keys", path],
    queryFn: () => workspacesApi.getIndexKeyDetail(workspaceName, path),
    enabled,
  });
}

export function usePatchStrategy(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ path, strategy }: { path: string; strategy: IndexKeyStrategy }) =>
      workspacesApi.patchIndexKeyStrategy(workspaceName, path, { strategy }),
    onSuccess: () => {
      void qc.invalidateQueries({
        queryKey: ["workspace", workspaceName, "index-keys"],
      });
    },
  });
}
```

- [ ] **Vérifier TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

Résultat attendu : pas d'erreur

- [ ] **Commit**

```bash
git add frontend/src/hooks/useIndexKeys.ts
git commit -m "feat(frontend): hooks useIndexKeys, useIndexKeyDetail, usePatchStrategy"
```

---

## Task 13 — Frontend : `WorkspaceIndexTab`, i18n, câblage dans `WorkspaceDetailPanel`

**Files:**
- Create: `frontend/src/pages/workspace/WorkspaceIndexTab.tsx`
- Modify: `frontend/src/i18n/fr/workspace.json`
- Modify: `frontend/src/i18n/en/workspace.json`
- Modify: `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx`

- [ ] **Ajouter les clés i18n**

Dans `frontend/src/i18n/fr/workspace.json`, à l'intérieur de l'objet `"tabs"` existant, ajouter :

```json
"index": "Index"
```

Et ajouter une section de premier niveau `"index"` :

```json
  "index": {
    "title": "Clés d'index ({{count}})",
    "empty": "Aucun fichier indexé.",
    "search_placeholder": "Filtrer par chemin…",
    "strategy_replace": "replace",
    "strategy_append": "append",
    "badge_file": "via fichier",
    "toggle_tooltip_file": "Défini par .rag/strategy.yml — modifiable uniquement dans le fichier",
    "stats": "{{chunks}} chunks · {{versions}} version(s)",
    "last_indexed": "Indexé {{when}}",
    "version_label": "Version du {{date}}",
    "chunk_label": "Chunk #{{index}}",
    "metadata_label": "Metadata"
  }
```

Dans `frontend/src/i18n/en/workspace.json`, à l'intérieur de `"tabs"` :

```json
"index": "Index"
```

Et la section `"index"` :

```json
  "index": {
    "title": "Index keys ({{count}})",
    "empty": "No indexed files.",
    "search_placeholder": "Filter by path…",
    "strategy_replace": "replace",
    "strategy_append": "append",
    "badge_file": "from file",
    "toggle_tooltip_file": "Set by .rag/strategy.yml — edit the file to change",
    "stats": "{{chunks}} chunks · {{versions}} version(s)",
    "last_indexed": "Indexed {{when}}",
    "version_label": "Version from {{date}}",
    "chunk_label": "Chunk #{{index}}",
    "metadata_label": "Metadata"
  }
```

- [ ] **Créer `WorkspaceIndexTab.tsx`**

```tsx
// frontend/src/pages/workspace/WorkspaceIndexTab.tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useIndexKeyDetail, useIndexKeys, usePatchStrategy } from "@/hooks/useIndexKeys";
import { formatRelativeTime } from "@/lib/relativeTime";
import type { PathStrategyEntry } from "@/lib/workspaces.types";

interface Props {
  workspaceName: string;
  enabled: boolean;
}

export function WorkspaceIndexTab({ workspaceName, enabled }: Props) {
  const { t } = useTranslation("workspace");
  const { data, isLoading } = useIndexKeys(workspaceName, enabled);
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (isLoading) return <LoadingSpinner />;

  const paths = (data?.paths ?? []).filter((e) =>
    e.path.toLowerCase().includes(filter.toLowerCase()),
  );

  const toggle = (path: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">
          {t("index.title", { count: data?.total ?? 0 })}
        </h3>
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={t("index.search_placeholder")}
          className="h-7 rounded border border-slate-300 px-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
      </div>

      {paths.length === 0 ? (
        <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("index.empty")}
        </div>
      ) : (
        <div className="space-y-1">
          {paths.map((entry) => (
            <PathRow
              key={entry.path}
              entry={entry}
              workspaceName={workspaceName}
              isOpen={expanded.has(entry.path)}
              onToggle={() => toggle(entry.path)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface PathRowProps {
  entry: PathStrategyEntry;
  workspaceName: string;
  isOpen: boolean;
  onToggle: () => void;
}

function PathRow({ entry, workspaceName, isOpen, onToggle }: PathRowProps) {
  const { t } = useTranslation("workspace");
  const patch = usePatchStrategy(workspaceName);
  const { data: detail, isLoading: detailLoading } = useIndexKeyDetail(
    workspaceName,
    entry.path,
    isOpen,
  );

  const isFromFile = entry.updated_by === "strategy_file";
  const isAppend = entry.strategy === "append";

  const handleStrategyToggle = (checked: boolean) => {
    patch.mutate({ path: entry.path, strategy: checked ? "append" : "replace" });
  };

  return (
    <div className="rounded border border-slate-200 bg-white">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-slate-50"
      >
        <div className="flex items-center gap-2 text-sm min-w-0">
          {isOpen ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0" />
          )}
          <code className="font-mono text-xs truncate">{entry.path}</code>
          <span
            className={`rounded px-1.5 py-0.5 text-xs font-medium shrink-0 ${
              isAppend
                ? "bg-blue-100 text-blue-700"
                : "bg-slate-100 text-slate-500"
            }`}
          >
            {isAppend ? t("index.strategy_append") : t("index.strategy_replace")}
          </span>
          {isFromFile && (
            <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-amber-100 text-amber-700 shrink-0">
              {t("index.badge_file")}
            </span>
          )}
          <span className="text-slate-400 text-xs shrink-0">
            {t("index.stats", {
              chunks: entry.chunk_count,
              versions: entry.version_count,
            })}
          </span>
        </div>

        <div
          className="flex items-center gap-2 shrink-0"
          onClick={(e) => e.stopPropagation()}
        >
          {isFromFile ? (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span>
                    <Switch checked={isAppend} disabled />
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="max-w-xs text-xs">{t("index.toggle_tooltip_file")}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          ) : (
            <Switch
              checked={isAppend}
              onCheckedChange={handleStrategyToggle}
              disabled={patch.isPending}
            />
          )}
        </div>
      </button>

      {isOpen && (
        <div className="border-t border-slate-100 bg-slate-50 px-3 py-2 space-y-3">
          {detailLoading ? (
            <LoadingSpinner />
          ) : (
            (detail?.versions ?? []).map((vg) => (
              <div key={vg.indexed_at} className="space-y-1">
                <p className="text-xs font-semibold text-slate-600">
                  {t("index.version_label", {
                    date: new Date(vg.indexed_at).toLocaleString(),
                  })}
                </p>
                {vg.chunks.map((chunk) => (
                  <div
                    key={chunk.chunk_index}
                    className="rounded border border-slate-200 bg-white p-2 text-xs"
                  >
                    <p className="font-medium text-slate-500 mb-1">
                      {t("index.chunk_label", { index: chunk.chunk_index })}
                    </p>
                    <p className="text-slate-700 whitespace-pre-wrap line-clamp-4">
                      {chunk.content}
                    </p>
                    {Object.keys(chunk.metadata).length > 0 && (
                      <details className="mt-1">
                        <summary className="cursor-pointer text-slate-400">
                          {t("index.metadata_label")}
                        </summary>
                        <pre className="mt-1 text-xs text-slate-500 overflow-auto">
                          {JSON.stringify(chunk.metadata, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                ))}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Câbler l'onglet dans `WorkspaceDetailPanel.tsx`**

Ajouter l'import en tête :

```typescript
import { WorkspaceIndexTab } from "./WorkspaceIndexTab";
```

Dans `<TabsList>`, après `<TabsTrigger value="jobs">`, ajouter :

```tsx
          <TabsTrigger value="index">{t("tabs.index")}</TabsTrigger>
```

Dans les `<TabsContent>`, après `<TabsContent value="jobs" ...>`, ajouter :

```tsx
        <TabsContent value="index" className="pt-4">
          <WorkspaceIndexTab workspaceName={ws.name} enabled={activeTab === "index"} />
        </TabsContent>
```

- [ ] **Vérifier TypeScript et lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Résultat attendu : pas d'erreur

- [ ] **Commit**

```bash
git add frontend/src/pages/workspace/WorkspaceIndexTab.tsx \
        frontend/src/pages/workspace/WorkspaceDetailPanel.tsx \
        frontend/src/i18n/fr/workspace.json \
        frontend/src/i18n/en/workspace.json
git commit -m "feat(frontend): onglet Index — visualisation clés, chunks, toggle stratégie"
```

---

## Task 14 — Tests frontend `WorkspaceIndexTab`

**Files:**
- Create: `frontend/src/pages/workspace/__tests__/WorkspaceIndexTab.test.tsx`

- [ ] **Écrire les tests**

```tsx
// frontend/src/pages/workspace/__tests__/WorkspaceIndexTab.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import i18n from "@/lib/i18n";
import { WorkspaceIndexTab } from "../WorkspaceIndexTab";
import { workspacesApi } from "@/lib/workspaces";

vi.mock("@/lib/workspaces");

const mockedApi = vi.mocked(workspacesApi);

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("WorkspaceIndexTab", () => {
  it("affiche 'Aucun fichier indexé' quand la liste est vide", async () => {
    mockedApi.listIndexKeys.mockResolvedValue({ paths: [], total: 0 });
    render(<WorkspaceIndexTab workspaceName="ws1" enabled />, { wrapper });
    await waitFor(() =>
      expect(screen.getByText(/aucun fichier indexé/i)).toBeInTheDocument(),
    );
  });

  it("affiche les paths indexés", async () => {
    mockedApi.listIndexKeys.mockResolvedValue({
      total: 1,
      paths: [
        {
          path: "LESSONS.md",
          strategy: "replace",
          updated_by: "ui",
          chunk_count: 3,
          version_count: 1,
          last_indexed_at: null,
        },
      ],
    });
    render(<WorkspaceIndexTab workspaceName="ws1" enabled />, { wrapper });
    await waitFor(() =>
      expect(screen.getByText("LESSONS.md")).toBeInTheDocument(),
    );
  });

  it("filtre les paths selon la saisie", async () => {
    mockedApi.listIndexKeys.mockResolvedValue({
      total: 2,
      paths: [
        {
          path: "LESSONS.md",
          strategy: "replace",
          updated_by: "ui",
          chunk_count: 1,
          version_count: 1,
          last_indexed_at: null,
        },
        {
          path: "docs/api.md",
          strategy: "replace",
          updated_by: "ui",
          chunk_count: 2,
          version_count: 1,
          last_indexed_at: null,
        },
      ],
    });
    render(<WorkspaceIndexTab workspaceName="ws1" enabled />, { wrapper });
    await waitFor(() => screen.getByText("LESSONS.md"));

    const input = screen.getByPlaceholderText(/filtrer/i);
    await userEvent.type(input, "docs");

    expect(screen.queryByText("LESSONS.md")).not.toBeInTheDocument();
    expect(screen.getByText("docs/api.md")).toBeInTheDocument();
  });

  it("désactive le toggle quand la stratégie vient du fichier", async () => {
    mockedApi.listIndexKeys.mockResolvedValue({
      total: 1,
      paths: [
        {
          path: "LESSONS.md",
          strategy: "append",
          updated_by: "strategy_file",
          chunk_count: 2,
          version_count: 2,
          last_indexed_at: null,
        },
      ],
    });
    render(<WorkspaceIndexTab workspaceName="ws1" enabled />, { wrapper });
    await waitFor(() => screen.getByText("LESSONS.md"));

    const toggle = screen.getByRole("switch");
    expect(toggle).toBeDisabled();
  });

  it("appelle patchIndexKeyStrategy au toggle actif", async () => {
    mockedApi.listIndexKeys.mockResolvedValue({
      total: 1,
      paths: [
        {
          path: "README.md",
          strategy: "replace",
          updated_by: "ui",
          chunk_count: 1,
          version_count: 1,
          last_indexed_at: null,
        },
      ],
    });
    mockedApi.patchIndexKeyStrategy.mockResolvedValue(undefined);
    render(<WorkspaceIndexTab workspaceName="ws1" enabled />, { wrapper });
    await waitFor(() => screen.getByText("README.md"));

    const toggle = screen.getByRole("switch");
    await userEvent.click(toggle);

    expect(mockedApi.patchIndexKeyStrategy).toHaveBeenCalledWith(
      "ws1",
      "README.md",
      { strategy: "append" },
    );
  });
});
```

- [ ] **Vérifier que les tests passent**

```bash
cd frontend && npm test -- WorkspaceIndexTab
```

Résultat attendu : `5 passed`

- [ ] **Vérifier absence de régressions**

```bash
cd frontend && npm test
```

Résultat attendu : tous les tests passent

- [ ] **Commit final**

```bash
git add frontend/src/pages/workspace/__tests__/WorkspaceIndexTab.test.tsx
git commit -m "test(frontend): WorkspaceIndexTab — liste, filtre, toggle, strategy_file disabled"
```

---

## Récapitulatif des commits

| # | Message |
|---|---------|
| 1 | `chore(db): migration 035 — table path_strategies` |
| 2 | `feat(db): path_strategies CRUD — get_strategy, upsert, batch, get_all` |
| 3 | `feat(db): upsert_chunks — paramètre strategy replace/append` |
| 4 | `feat(db): index_keys — list_paths_aggregate et get_path_chunks` |
| 5 | `feat(schemas): index_keys — PathStrategyEntry, IndexKeysResponse, PathDetailResponse` |
| 6 | `feat(api): router admin_index_keys — GET list, GET detail, PATCH strategy` |
| 7 | `test(api): couverture admin_index_keys — GET list/detail, PATCH, 404, 422` |
| 8 | `feat(indexer): RealIndexer lit la stratégie par path avant upsert_chunks` |
| 9 | `feat(sync): strategy_config — parse_strategy_file lit .rag/strategy.yml` |
| 10 | `feat(sync): executor — lit .rag/strategy.yml après git pull et UPSERT strategies` |
| 11 | `feat(frontend): types et API client index-keys` |
| 12 | `feat(frontend): hooks useIndexKeys, useIndexKeyDetail, usePatchStrategy` |
| 13 | `feat(frontend): onglet Index — visualisation clés, chunks, toggle stratégie` |
| 14 | `test(frontend): WorkspaceIndexTab — liste, filtre, toggle, strategy_file disabled` |
