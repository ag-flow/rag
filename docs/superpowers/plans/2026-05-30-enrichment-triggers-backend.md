# Enrichissement LLM par Extension — Backend (Jalon 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Après chaque indexation de fichier, détecter les triggers configurés pour l'extension et exécuter séquentiellement des prompts LLM dont les résultats sont réindexés dans pgvector sous `{path}::{metadata_key}`.

**Architecture:** Nouveaux services CRUD (prompt_templates, triggers) + moteur d'enrichissement qui réutilise `indexer.index_file` / `delete_file` pour les chemins dérivés. Injection dans `executor.py` après chaque `index_file`. Migrations 031 déjà appliquées.

**Tech Stack:** Python 3.12 / asyncpg / FastAPI / pytest-asyncio — libs anthropic/openai déjà installées

---

## Structure des fichiers

### Backend (créer)
- `backend/src/rag/schemas/enrichments.py`
- `backend/src/rag/services/prompt_templates.py`
- `backend/src/rag/services/triggers.py`
- `backend/src/rag/services/enrichments.py`
- `backend/src/rag/api/enrichments.py`
- `backend/tests/unit/test_enrichments.py`

### Backend (modifier)
- `backend/src/rag/sync/executor.py` — injection après index_file
- `backend/src/rag/services/webhook_dispatch.py` — enrichments dans payload
- `backend/src/rag/main.py` — router

---

## Task 1 : Schemas enrichments.py

**Files:**
- Create: `backend/src/rag/schemas/enrichments.py`

- [ ] **Créer `backend/src/rag/schemas/enrichments.py`**

```python
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PromptTemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    language: str = Field(min_length=1, max_length=64)
    description: str | None = None
    metadata_key: str = Field(min_length=1, max_length=64)
    result_type: str = Field(default="text")  # "text" | "json"
    result_schema: dict[str, Any] | None = None
    prompt: str = Field(min_length=1)


class PromptTemplatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    prompt: str | None = None
    result_schema: dict[str, Any] | None = None


class PromptTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    language: str
    description: str | None
    metadata_key: str
    result_type: str
    result_schema: dict[str, Any] | None
    prompt: str
    created_at: datetime
    updated_at: datetime


class TriggerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extension: str = Field(min_length=2, max_length=16)  # ex: ".cs"
    enabled: bool = True


class TriggerPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class TriggerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    extension: str
    enabled: bool
    created_at: datetime


class TriggerPromptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: UUID
    llm_id: UUID
    order_index: int = Field(ge=1)
    enabled: bool = True


class TriggerPromptPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    order_index: int | None = Field(default=None, ge=1)


class TriggerPromptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_id: UUID
    template_name: str
    llm_id: UUID
    llm_provider: str
    llm_model: str
    order_index: int
    enabled: bool
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/schemas/enrichments.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/schemas/enrichments.py
git commit -m "feat(schemas): enrichment triggers — PromptTemplate + Trigger + TriggerPrompt DTOs"
```

---

## Task 2 : Services CRUD prompt_templates + triggers

**Files:**
- Create: `backend/src/rag/services/prompt_templates.py`
- Create: `backend/src/rag/services/triggers.py`

- [ ] **Créer `backend/src/rag/services/prompt_templates.py`**

```python
from __future__ import annotations

import asyncpg
import structlog

from rag.schemas.enrichments import PromptTemplateCreate, PromptTemplateOut, PromptTemplatePatch

log = structlog.get_logger(__name__)


async def list_prompt_templates(conn: asyncpg.Connection) -> list[PromptTemplateOut]:
    rows = await conn.fetch(
        "SELECT id, name, language, description, metadata_key, result_type, "
        "result_schema, prompt, created_at, updated_at "
        "FROM prompt_templates ORDER BY language, name"
    )
    return [PromptTemplateOut.model_validate(dict(r)) for r in rows]


async def get_prompt_template(
    conn: asyncpg.Connection, template_id: str
) -> PromptTemplateOut | None:
    row = await conn.fetchrow(
        "SELECT id, name, language, description, metadata_key, result_type, "
        "result_schema, prompt, created_at, updated_at "
        "FROM prompt_templates WHERE id = $1::uuid",
        template_id,
    )
    return PromptTemplateOut.model_validate(dict(row)) if row else None


async def create_prompt_template(
    conn: asyncpg.Connection, req: PromptTemplateCreate
) -> PromptTemplateOut:
    import json
    row = await conn.fetchrow(
        "INSERT INTO prompt_templates "
        "(name, language, description, metadata_key, result_type, result_schema, prompt) "
        "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7) "
        "RETURNING id, name, language, description, metadata_key, result_type, "
        "result_schema, prompt, created_at, updated_at",
        req.name, req.language, req.description, req.metadata_key,
        req.result_type,
        json.dumps(req.result_schema) if req.result_schema else None,
        req.prompt,
    )
    log.info("prompt_template.created", name=req.name)
    return PromptTemplateOut.model_validate(dict(row))


async def patch_prompt_template(
    conn: asyncpg.Connection, template_id: str, req: PromptTemplatePatch
) -> PromptTemplateOut | None:
    import json
    row = await conn.fetchrow(
        "UPDATE prompt_templates SET "
        "description = COALESCE($2, description), "
        "prompt = COALESCE($3, prompt), "
        "result_schema = COALESCE($4::jsonb, result_schema), "
        "updated_at = now() "
        "WHERE id = $1::uuid "
        "RETURNING id, name, language, description, metadata_key, result_type, "
        "result_schema, prompt, created_at, updated_at",
        template_id,
        req.description,
        req.prompt,
        json.dumps(req.result_schema) if req.result_schema else None,
    )
    return PromptTemplateOut.model_validate(dict(row)) if row else None


async def delete_prompt_template(
    conn: asyncpg.Connection, template_id: str
) -> bool:
    """Supprime si non référencé par un trigger actif. Retourne False si référencé."""
    ref_count = await conn.fetchval(
        "SELECT count(*) FROM workspace_extension_trigger_prompts WHERE template_id = $1::uuid",
        template_id,
    )
    if int(ref_count or 0) > 0:
        return False
    result = await conn.execute(
        "DELETE FROM prompt_templates WHERE id = $1::uuid", template_id
    )
    return result != "DELETE 0"
```

- [ ] **Créer `backend/src/rag/services/triggers.py`**

```python
from __future__ import annotations

from uuid import UUID

import asyncpg
import structlog

from rag.schemas.enrichments import (
    TriggerCreate,
    TriggerOut,
    TriggerPatch,
    TriggerPromptCreate,
    TriggerPromptOut,
    TriggerPromptPatch,
)

log = structlog.get_logger(__name__)


async def list_triggers(
    conn: asyncpg.Connection, *, workspace_name: str
) -> list[TriggerOut]:
    rows = await conn.fetch(
        """
        SELECT t.id, t.extension, t.enabled, t.created_at
        FROM workspace_extension_triggers t
        JOIN workspaces w ON w.id = t.workspace_id
        WHERE w.name = $1
        ORDER BY t.extension
        """,
        workspace_name,
    )
    return [TriggerOut.model_validate(dict(r)) for r in rows]


async def create_trigger(
    conn: asyncpg.Connection, *, workspace_name: str, req: TriggerCreate
) -> TriggerOut:
    row = await conn.fetchrow(
        """
        INSERT INTO workspace_extension_triggers (workspace_id, extension, enabled)
        SELECT w.id, $2, $3 FROM workspaces w WHERE w.name = $1
        RETURNING id, extension, enabled, created_at
        """,
        workspace_name, req.extension, req.enabled,
    )
    if row is None:
        raise ValueError(f"workspace {workspace_name!r} not found")
    log.info("trigger.created", workspace=workspace_name, extension=req.extension)
    return TriggerOut.model_validate(dict(row))


async def patch_trigger(
    conn: asyncpg.Connection, *, workspace_name: str, trigger_id: str, req: TriggerPatch
) -> TriggerOut | None:
    row = await conn.fetchrow(
        """
        UPDATE workspace_extension_triggers t SET enabled = $3
        FROM workspaces w
        WHERE w.id = t.workspace_id AND w.name = $1 AND t.id = $2::uuid
        RETURNING t.id, t.extension, t.enabled, t.created_at
        """,
        workspace_name, trigger_id, req.enabled,
    )
    return TriggerOut.model_validate(dict(row)) if row else None


async def delete_trigger(
    conn: asyncpg.Connection, *, workspace_name: str, trigger_id: str
) -> bool:
    result = await conn.execute(
        """
        DELETE FROM workspace_extension_triggers t
        USING workspaces w
        WHERE w.id = t.workspace_id AND w.name = $1 AND t.id = $2::uuid
        """,
        workspace_name, trigger_id,
    )
    return result != "DELETE 0"


async def list_trigger_prompts(
    conn: asyncpg.Connection, *, trigger_id: str
) -> list[TriggerPromptOut]:
    rows = await conn.fetch(
        """
        SELECT tp.id, tp.template_id, pt.name AS template_name,
               tp.llm_id, lc.provider AS llm_provider, lc.model AS llm_model,
               tp.order_index, tp.enabled
        FROM workspace_extension_trigger_prompts tp
        JOIN prompt_templates pt ON pt.id = tp.template_id
        JOIN workspace_llm_configs lc ON lc.id = tp.llm_id
        WHERE tp.trigger_id = $1::uuid
        ORDER BY tp.order_index
        """,
        trigger_id,
    )
    return [TriggerPromptOut.model_validate(dict(r)) for r in rows]


async def create_trigger_prompt(
    conn: asyncpg.Connection, *, trigger_id: str, req: TriggerPromptCreate
) -> TriggerPromptOut:
    row = await conn.fetchrow(
        """
        INSERT INTO workspace_extension_trigger_prompts
            (trigger_id, template_id, llm_id, order_index, enabled)
        VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5)
        RETURNING id, template_id, llm_id, order_index, enabled
        """,
        trigger_id, str(req.template_id), str(req.llm_id), req.order_index, req.enabled,
    )
    # Recharge avec JOINs pour les noms
    return (await list_trigger_prompts(conn, trigger_id=trigger_id))[
        next(i for i, r in enumerate(await conn.fetch(
            "SELECT id FROM workspace_extension_trigger_prompts WHERE trigger_id=$1::uuid ORDER BY order_index",
            trigger_id
        )) if r["id"] == row["id"])
    ]


async def patch_trigger_prompt(
    conn: asyncpg.Connection, *, prompt_id: str, req: TriggerPromptPatch
) -> TriggerPromptOut | None:
    updates = []
    params: list = [prompt_id]
    if req.enabled is not None:
        params.append(req.enabled)
        updates.append(f"enabled = ${len(params)}")
    if req.order_index is not None:
        params.append(req.order_index)
        updates.append(f"order_index = ${len(params)}")
    if not updates:
        # Rien à mettre à jour → reload
        row = await conn.fetchrow(
            "SELECT trigger_id FROM workspace_extension_trigger_prompts WHERE id=$1::uuid",
            prompt_id,
        )
        if row is None:
            return None
        prompts = await list_trigger_prompts(conn, trigger_id=str(row["trigger_id"]))
        return next((p for p in prompts if str(p.id) == prompt_id), None)

    await conn.execute(
        f"UPDATE workspace_extension_trigger_prompts SET {', '.join(updates)} WHERE id=$1::uuid",
        *params,
    )
    row = await conn.fetchrow(
        "SELECT trigger_id FROM workspace_extension_trigger_prompts WHERE id=$1::uuid",
        prompt_id,
    )
    if row is None:
        return None
    prompts = await list_trigger_prompts(conn, trigger_id=str(row["trigger_id"]))
    return next((p for p in prompts if str(p.id) == prompt_id), None)


async def delete_trigger_prompt(
    conn: asyncpg.Connection, *, prompt_id: str
) -> bool:
    result = await conn.execute(
        "DELETE FROM workspace_extension_trigger_prompts WHERE id=$1::uuid", prompt_id
    )
    return result != "DELETE 0"
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/services/prompt_templates.py src/rag/services/triggers.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/services/prompt_templates.py backend/src/rag/services/triggers.py
git commit -m "feat(services): CRUD prompt_templates + triggers"
```

---

## Task 3 : Service enrichments.py (TDD)

**Files:**
- Create: `backend/src/rag/services/enrichments.py`
- Create: `backend/tests/unit/test_enrichments.py`

- [ ] **Écrire les tests (rouge)**

```python
# backend/tests/unit/test_enrichments.py
from __future__ import annotations

from hashlib import sha256
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag.services.enrichments import run_enrichments


def _make_conn(trigger_rows=None, enrichment_rows=None):
    """Crée un mock de connexion asyncpg."""
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=trigger_rows or [])
    conn.fetchrow = AsyncMock(return_value=enrichment_rows)
    conn.execute = AsyncMock(return_value="UPDATE 1")
    conn.fetchval = AsyncMock(return_value=None)
    return conn


def _trigger_row(
    template_id="tid1",
    llm_id="lid1",
    order_index=1,
    metadata_key="documentation",
    result_type="text",
    prompt="Génère la doc de: {content}",
    llm_provider="openai",
    llm_model="gpt-4o",
    api_key_ref=None,
):
    return {
        "template_id": template_id,
        "llm_id": llm_id,
        "order_index": order_index,
        "metadata_key": metadata_key,
        "result_type": result_type,
        "prompt": prompt,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "api_key_ref": api_key_ref,
    }


@pytest.mark.asyncio
async def test_run_enrichments_no_trigger() -> None:
    """Si aucun trigger pour l'extension → retourne liste vide."""
    conn = _make_conn(trigger_rows=[])
    indexer = MagicMock()

    results = await run_enrichments(
        conn=conn,
        indexer=indexer,
        workspace_id="ws1",
        workspace_name="test-ws",
        path="src/main.rs",
        content="fn main() {}",
        content_hash="sha256:abc",
        vault_svc=MagicMock(),
        client_provider=MagicMock(),
    )

    assert results == []
    indexer.index_file.assert_not_called()


@pytest.mark.asyncio
async def test_run_enrichments_calls_llm_and_indexes() -> None:
    """Trigger actif → LLM appelé + index_file au path enrichi."""
    conn = _make_conn(trigger_rows=[_trigger_row()])
    conn.fetchrow = AsyncMock(return_value=None)  # pas d'enrichissement existant

    indexer = MagicMock()
    indexer.index_file = AsyncMock(return_value=1)

    with patch("rag.services.enrichments.call_llm", new=AsyncMock(return_value={
        "answer": "Documentation générée.", "usage": {"prompt_tokens": 100, "completion_tokens": 50}
    })):
        results = await run_enrichments(
            conn=conn,
            indexer=indexer,
            workspace_id="ws1",
            workspace_name="test-ws",
            path="src/service.cs",
            content="class Foo {}",
            content_hash="sha256:xyz",
            vault_svc=MagicMock(),
            client_provider=MagicMock(),
        )

    assert len(results) == 1
    assert results[0]["metadata_key"] == "documentation"
    assert results[0]["status"] == "done"
    indexer.index_file.assert_called_once()
    # Vérifier que le path enrichi est bien src/service.cs::documentation
    call_kwargs = indexer.index_file.call_args.kwargs
    assert call_kwargs["path"] == "src/service.cs::documentation"


@pytest.mark.asyncio
async def test_run_enrichments_skips_if_hash_unchanged() -> None:
    """Si content_hash == enrichissement existant → skip."""
    existing_hash = sha256("class Foo {}".encode()).hexdigest()
    conn = _make_conn(trigger_rows=[_trigger_row()])
    conn.fetchrow = AsyncMock(return_value={
        "result_hash": existing_hash,
        "id": "enr1",
    })

    indexer = MagicMock()
    indexer.index_file = AsyncMock()

    results = await run_enrichments(
        conn=conn,
        indexer=indexer,
        workspace_id="ws1",
        workspace_name="test-ws",
        path="src/service.cs",
        content="class Foo {}",
        content_hash=f"sha256:{existing_hash}",
        vault_svc=MagicMock(),
        client_provider=MagicMock(),
    )

    assert results[0]["status"] == "skipped"
    indexer.index_file.assert_not_called()


@pytest.mark.asyncio
async def test_run_enrichments_cleans_on_empty_result() -> None:
    """Résultat vide → delete_file + suppression document_enrichments."""
    conn = _make_conn(trigger_rows=[_trigger_row()])
    conn.fetchrow = AsyncMock(return_value={"result_hash": "old", "id": "enr1"})

    indexer = MagicMock()
    indexer.delete_file = AsyncMock()
    indexer.index_file = AsyncMock()

    with patch("rag.services.enrichments.call_llm", new=AsyncMock(return_value={
        "answer": "   ", "usage": {"prompt_tokens": 10, "completion_tokens": 0}
    })):
        results = await run_enrichments(
            conn=conn,
            indexer=indexer,
            workspace_id="ws1",
            workspace_name="test-ws",
            path="src/service.cs",
            content="changed content",
            content_hash="sha256:newHash",
            vault_svc=MagicMock(),
            client_provider=MagicMock(),
        )

    assert results[0]["status"] == "empty"
    indexer.delete_file.assert_called_once()
    indexer.index_file.assert_not_called()
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_enrichments.py --collect-only 2>&1 | head -10
```

Résultat attendu : ImportError.

- [ ] **Créer `backend/src/rag/services/enrichments.py`**

```python
from __future__ import annotations

import asyncio
from hashlib import sha256
from typing import Any

import asyncpg
import structlog

from rag.services.llm_clients import call_llm

log = structlog.get_logger(__name__)


async def _resolve_harpo(harpo_path: str, vault_svc: Any, client_provider: Any, config_pool: Any) -> str | None:
    """Résout un harpo_path → valeur secrète."""
    from rag.secrets.refs import is_vault_ref, parse_ref
    if not is_vault_ref(harpo_path):
        return None
    vault_name, secret_path = parse_ref(harpo_path)
    async with config_pool.acquire() as conn:
        vault = await vault_svc.get_by_name(conn, vault_name)
    if vault is None:
        return None
    client = await client_provider.get_client(vault.api_key_id)
    return await asyncio.to_thread(client.get_secret, secret_path)


async def run_enrichments(
    *,
    conn: asyncpg.Connection,
    indexer: Any,
    workspace_id: str,
    workspace_name: str,
    path: str,
    content: str,
    content_hash: str,
    vault_svc: Any,
    client_provider: Any,
    config_pool: Any | None = None,
) -> list[dict[str, Any]]:
    """Exécute les trigger prompts actifs pour l'extension de `path`.

    Retourne la liste des résultats : [{metadata_key, status, template_name, result_type}, ...]
    """
    import pathlib
    extension = pathlib.Path(path).suffix.lower()
    if not extension:
        return []

    # Charger les trigger prompts actifs pour (workspace_id, extension)
    trigger_prompts = await conn.fetch(
        """
        SELECT
            tp.id AS tp_id,
            tp.template_id,
            pt.name AS template_name,
            pt.metadata_key,
            pt.result_type,
            pt.prompt,
            tp.llm_id,
            lc.provider AS llm_provider,
            lc.model AS llm_model,
            lc.api_key_ref,
            lc.base_url AS llm_base_url
        FROM workspace_extension_trigger_prompts tp
        JOIN workspace_extension_triggers t ON t.id = tp.trigger_id
        JOIN workspaces w ON w.id = t.workspace_id
        JOIN prompt_templates pt ON pt.id = tp.template_id
        JOIN workspace_llm_configs lc ON lc.id = tp.llm_id
        WHERE w.id = $1::uuid
          AND t.extension = $2
          AND t.enabled = true
          AND tp.enabled = true
          AND lc.enabled = true
        ORDER BY tp.order_index
        """,
        workspace_id,
        extension,
    )

    if not trigger_prompts:
        return []

    results: list[dict[str, Any]] = []
    # Hash du contenu source (sans préfixe "sha256:")
    src_hash = content_hash.removeprefix("sha256:")

    for row in trigger_prompts:
        template_id = str(row["template_id"])
        metadata_key = row["metadata_key"]
        enriched_path = f"{path}::{metadata_key}"

        # Vérifier si enrichissement existant avec même hash source
        existing = await conn.fetchrow(
            "SELECT id, result_hash FROM document_enrichments "
            "WHERE workspace_id = $1::uuid AND path = $2 AND template_id = $3::uuid",
            workspace_id, path, template_id,
        )

        if existing and existing["result_hash"] == src_hash:
            results.append({
                "path": path,
                "metadata_key": metadata_key,
                "template": row["template_name"],
                "result_type": row["result_type"],
                "status": "skipped",
            })
            continue

        # Résoudre la clé LLM
        llm_api_key: str | None = None
        if row["api_key_ref"] and config_pool:
            llm_api_key = await _resolve_harpo(
                row["api_key_ref"], vault_svc, client_provider, config_pool
            )

        # Substituer {content} dans le prompt
        prompt_text = row["prompt"].replace("{content}", content)

        # Appel LLM
        llm_result = await call_llm(
            provider=row["llm_provider"],
            model=row["llm_model"],
            api_key=llm_api_key,
            base_url=row["llm_base_url"],
            system_prompt="",  # pas de system séparé — le prompt contient tout
            messages=[{"role": "user", "content": prompt_text}],
        )
        answer = (llm_result["answer"] or "").strip()

        if not answer:
            # Résultat vide → cleanup
            await indexer.delete_file(workspace_id=workspace_id, path=enriched_path)
            if existing:
                await conn.execute(
                    "DELETE FROM document_enrichments WHERE id = $1::uuid", existing["id"]
                )
            results.append({
                "path": path,
                "metadata_key": metadata_key,
                "template": row["template_name"],
                "result_type": row["result_type"],
                "status": "empty",
                "previous_enrichment_deleted": existing is not None,
            })
            continue

        # Indexer le résultat
        await indexer.index_file(
            workspace_id=workspace_id,
            path=enriched_path,
            content=answer,
            content_hash=f"sha256:{sha256(answer.encode()).hexdigest()}",
            indexer_used=f"{row['llm_provider']}/{row['llm_model']}",
        )

        # Upsert document_enrichments
        import json
        await conn.execute(
            """
            INSERT INTO document_enrichments
                (workspace_id, path, template_id, metadata_key, result_type,
                 result, result_hash, llm_provider, llm_model, indexed_at)
            VALUES ($1::uuid, $2, $3::uuid, $4, $5, $6, $7, $8, $9, now())
            ON CONFLICT (workspace_id, path, template_id)
            DO UPDATE SET
                result = EXCLUDED.result,
                result_hash = EXCLUDED.result_hash,
                llm_provider = EXCLUDED.llm_provider,
                llm_model = EXCLUDED.llm_model,
                indexed_at = now()
            """,
            workspace_id, path, template_id, metadata_key,
            row["result_type"], answer, src_hash,
            row["llm_provider"], row["llm_model"],
        )

        log.info(
            "enrichment.done",
            workspace=workspace_name,
            path=path,
            metadata_key=metadata_key,
        )
        results.append({
            "path": path,
            "metadata_key": metadata_key,
            "template": row["template_name"],
            "result_type": row["result_type"],
            "status": "done",
        })

    return results
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_enrichments.py -v
```

Résultat attendu : 4 tests PASS.

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/services/enrichments.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/services/enrichments.py backend/tests/unit/test_enrichments.py
git commit -m "feat(services): moteur d'enrichissement LLM avec déduplication"
```

---

## Task 4 : Router API + main.py

**Files:**
- Create: `backend/src/rag/api/enrichments.py`
- Modify: `backend/src/rag/main.py`

- [ ] **Créer `backend/src/rag/api/enrichments.py`**

```python
from __future__ import annotations

from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.schemas.enrichments import (
    PromptTemplateCreate,
    PromptTemplateOut,
    PromptTemplatePatch,
    TriggerCreate,
    TriggerOut,
    TriggerPatch,
    TriggerPromptCreate,
    TriggerPromptOut,
    TriggerPromptPatch,
)

log = structlog.get_logger(__name__)

_auth = [Depends(require_master_key_or_authenticated_admin)]


def _pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pools.config_pool  # type: ignore[no-any-return]


# ─── Bibliothèque globale de prompts ──────────────────────────────────────────

router_prompts = APIRouter(
    prefix="/api/admin/prompts",
    tags=["enrichment-prompts"],
    dependencies=_auth,
)


@router_prompts.get("", response_model=list[PromptTemplateOut])
async def list_prompts(request: Request) -> list[PromptTemplateOut]:
    from rag.services.prompt_templates import list_prompt_templates
    async with _pool(request).acquire() as conn:
        return await list_prompt_templates(conn)


@router_prompts.post("", response_model=PromptTemplateOut, status_code=201)
async def create_prompt(body: PromptTemplateCreate, request: Request) -> PromptTemplateOut:
    from rag.services.prompt_templates import create_prompt_template
    async with _pool(request).acquire() as conn:
        try:
            return await create_prompt_template(conn, body)
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise HTTPException(status.HTTP_409_CONFLICT, "name already exists") from exc
            raise


@router_prompts.get("/{template_id}", response_model=PromptTemplateOut)
async def get_prompt(template_id: UUID, request: Request) -> PromptTemplateOut:
    from rag.services.prompt_templates import get_prompt_template
    async with _pool(request).acquire() as conn:
        result = await get_prompt_template(conn, str(template_id))
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template not found")
    return result


@router_prompts.patch("/{template_id}", response_model=PromptTemplateOut)
async def patch_prompt(
    template_id: UUID, body: PromptTemplatePatch, request: Request
) -> PromptTemplateOut:
    from rag.services.prompt_templates import patch_prompt_template
    async with _pool(request).acquire() as conn:
        result = await patch_prompt_template(conn, str(template_id), body)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template not found")
    return result


@router_prompts.delete("/{template_id}", status_code=204)
async def delete_prompt(template_id: UUID, request: Request) -> Response:
    from rag.services.prompt_templates import delete_prompt_template
    async with _pool(request).acquire() as conn:
        deleted = await delete_prompt_template(conn, str(template_id))
    if not deleted:
        raise HTTPException(status.HTTP_409_CONFLICT, "template referenced by active trigger")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Triggers par workspace ────────────────────────────────────────────────────

router_triggers = APIRouter(
    prefix="/api/admin/workspaces/{workspace_name}/triggers",
    tags=["enrichment-triggers"],
    dependencies=_auth,
)


@router_triggers.get("", response_model=list[TriggerOut])
async def list_triggers(workspace_name: str, request: Request) -> list[TriggerOut]:
    from rag.services.triggers import list_triggers as _list
    async with _pool(request).acquire() as conn:
        return await _list(conn, workspace_name=workspace_name)


@router_triggers.post("", response_model=TriggerOut, status_code=201)
async def create_trigger(
    workspace_name: str, body: TriggerCreate, request: Request
) -> TriggerOut:
    from rag.services.triggers import create_trigger as _create
    async with _pool(request).acquire() as conn:
        try:
            return await _create(conn, workspace_name=workspace_name, req=body)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise HTTPException(status.HTTP_409_CONFLICT, "extension already has trigger") from exc
            raise


@router_triggers.patch("/{trigger_id}", response_model=TriggerOut)
async def patch_trigger(
    workspace_name: str, trigger_id: UUID, body: TriggerPatch, request: Request
) -> TriggerOut:
    from rag.services.triggers import patch_trigger as _patch
    async with _pool(request).acquire() as conn:
        result = await _patch(conn, workspace_name=workspace_name, trigger_id=str(trigger_id), req=body)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trigger not found")
    return result


@router_triggers.delete("/{trigger_id}", status_code=204)
async def delete_trigger(
    workspace_name: str, trigger_id: UUID, request: Request
) -> Response:
    from rag.services.triggers import delete_trigger as _delete
    async with _pool(request).acquire() as conn:
        deleted = await _delete(conn, workspace_name=workspace_name, trigger_id=str(trigger_id))
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trigger not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router_triggers.get("/{trigger_id}/prompts", response_model=list[TriggerPromptOut])
async def list_trigger_prompts(trigger_id: UUID, request: Request) -> list[TriggerPromptOut]:
    from rag.services.triggers import list_trigger_prompts as _list
    async with _pool(request).acquire() as conn:
        return await _list(conn, trigger_id=str(trigger_id))


@router_triggers.post("/{trigger_id}/prompts", response_model=TriggerPromptOut, status_code=201)
async def create_trigger_prompt(
    trigger_id: UUID, body: TriggerPromptCreate, request: Request
) -> TriggerPromptOut:
    from rag.services.triggers import create_trigger_prompt as _create
    async with _pool(request).acquire() as conn:
        try:
            return await _create(conn, trigger_id=str(trigger_id), req=body)
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise HTTPException(status.HTTP_409_CONFLICT, "order_index already used") from exc
            raise


@router_triggers.patch("/{trigger_id}/prompts/{prompt_id}", response_model=TriggerPromptOut)
async def patch_trigger_prompt(
    trigger_id: UUID, prompt_id: UUID, body: TriggerPromptPatch, request: Request
) -> TriggerPromptOut:
    from rag.services.triggers import patch_trigger_prompt as _patch
    async with _pool(request).acquire() as conn:
        result = await _patch(conn, prompt_id=str(prompt_id), req=body)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trigger prompt not found")
    return result


@router_triggers.delete("/{trigger_id}/prompts/{prompt_id}", status_code=204)
async def delete_trigger_prompt(
    trigger_id: UUID, prompt_id: UUID, request: Request
) -> Response:
    from rag.services.triggers import delete_trigger_prompt as _delete
    async with _pool(request).acquire() as conn:
        deleted = await _delete(conn, prompt_id=str(prompt_id))
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trigger prompt not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Enregistrer dans `main.py`**

Après les imports de routers, ajouter :
```python
from rag.api.enrichments import router_prompts as enrichment_prompts_router
from rag.api.enrichments import router_triggers as enrichment_triggers_router
```

Après les derniers `include_router` :
```python
app.include_router(enrichment_prompts_router)
app.include_router(enrichment_triggers_router)
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/api/enrichments.py src/rag/main.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/api/enrichments.py backend/src/rag/main.py
git commit -m "feat(api): enrichment triggers — CRUD prompts + triggers + trigger_prompts"
```

---

## Task 5 : Injection dans executor.py + webhook enrichi

**Files:**
- Modify: `backend/src/rag/sync/executor.py`
- Modify: `backend/src/rag/services/webhook_dispatch.py`

- [ ] **Lire `backend/src/rag/sync/executor.py`** entièrement (en particulier `_execute_git_job` et `_execute_push_job`).

- [ ] **Modifier `_execute_git_job` dans `executor.py`**

Dans `_execute_git_job`, après le bloc qui boucle sur `changes.added + changes.modified` :

```python
# Chercher le bloc :
        await indexer.index_file(
            workspace_id=job.workspace_id,
            path=path,
            content=content,
            content_hash=content_hash,
            indexer_used=job.indexer_used,
        )
        files_changed += 1
        changed_files.append((path, "added" if path in added_set else "modified"))
```

Remplacer par :

```python
        await indexer.index_file(
            workspace_id=job.workspace_id,
            path=path,
            content=content,
            content_hash=content_hash,
            indexer_used=job.indexer_used,
        )
        files_changed += 1
        changed_files.append((path, "added" if path in added_set else "modified"))

        # Enrichissements LLM post-indexation
        try:
            from rag.services.enrichments import run_enrichments
            async with config_pool.acquire() as _enrich_conn:
                _enrichments = await run_enrichments(
                    conn=_enrich_conn,
                    indexer=indexer,
                    workspace_id=str(job.workspace_id),
                    workspace_name=job.workspace_name,
                    path=path,
                    content=content,
                    content_hash=content_hash,
                    vault_svc=client_provider,  # HarpocrateClientProvider expose get_client
                    client_provider=client_provider,
                    config_pool=config_pool,
                )
                enrichment_results.extend(_enrichments)
        except Exception as _exc:
            log.warning("sync.executor.enrichment_failed", path=path, error=str(_exc))
```

**Initialiser `enrichment_results` avant la boucle** (après `changed_files: list = []`) :

```python
    enrichment_results: list[dict] = []
```

**Passer `enrichment_results` au dispatch webhook** : dans l'appel `dispatch_webhooks(...)`, ajouter `enrichments=enrichment_results`.

**Pour `_execute_push_job`** : même pattern (ajouter `enrichment_results = []` et l'appel `run_enrichments` après `index_file`).

- [ ] **Modifier `webhook_dispatch.py`** — ajouter `enrichments` dans le payload

Dans `dispatch_webhooks`, ajouter le paramètre :
```python
    enrichments: list[dict] | None = None,
```

Dans `_build_payload`, ajouter dans le dict retourné :
```python
        "enrichments": enrichments or [],
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/sync/executor.py src/rag/services/webhook_dispatch.py
```

- [ ] **Vérifier les tests existants**

```bash
cd backend && uv run pytest tests/unit/ -v --tb=short 2>&1 | tail -15
```

- [ ] **Commit**

```bash
git add backend/src/rag/sync/executor.py backend/src/rag/services/webhook_dispatch.py
git commit -m "feat(executor): enrichissements LLM post-indexation + webhook enrichi"
```
