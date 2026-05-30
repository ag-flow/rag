# RAG Playground — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un onglet Playground dans chaque workspace permettant de configurer des LLMs (Claude/OpenAI/Azure/Ollama) et de faire des requêtes ad hoc ancrées sur le RAG.

**Architecture:** Nouvelle table `workspace_llm_configs`, service CRUD + service de chat (embed query → vector_search → appel LLM), router FastAPI avec OIDC. Frontend : sous-onglets Config LLM et Chat dans WorkspaceDetailPanel.

**Tech Stack:** Python 3.12 / asyncpg / FastAPI / anthropic / openai / httpx — React 18 / TypeScript strict / TanStack Query / i18next

---

## Structure des fichiers

### Backend (créer)
- `backend/migrations/030_workspace_llm_configs.sql`
- `backend/src/rag/schemas/playground.py`
- `backend/src/rag/services/llm_configs.py`
- `backend/src/rag/services/llm_clients.py`
- `backend/src/rag/api/playground.py`
- `backend/tests/unit/test_llm_clients.py`

### Backend (modifier)
- `backend/pyproject.toml` — deps anthropic + openai
- `backend/src/rag/main.py` — enregistrer router playground

### Frontend (créer)
- `frontend/src/lib/playground.types.ts`
- `frontend/src/lib/playground.ts`
- `frontend/src/hooks/usePlayground.ts`
- `frontend/src/i18n/fr/playground.json`
- `frontend/src/i18n/en/playground.json`
- `frontend/src/pages/workspace/WorkspacePlaygroundTab.tsx`
- `frontend/src/pages/workspace/PlaygroundLlmConfigTab.tsx`
- `frontend/src/pages/workspace/PlaygroundChatTab.tsx`
- `frontend/src/pages/workspace/AddLlmConfigDialog.tsx`

### Frontend (modifier)
- `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx`
- `frontend/src/i18n/fr/workspace.json` — clé `tabs.playground`
- `frontend/src/i18n/en/workspace.json` — idem

---

## Task 1 : Migration + dépendances

**Files:**
- Create: `backend/migrations/030_workspace_llm_configs.sql`
- Modify: `backend/pyproject.toml`

- [ ] **Créer la migration**

```sql
-- backend/migrations/030_workspace_llm_configs.sql
-- Migration 030 — configs LLM par workspace (RAG Playground)

CREATE TABLE workspace_llm_configs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    provider     TEXT NOT NULL,
    model        TEXT NOT NULL,
    base_url     TEXT,
    api_key_ref  TEXT,
    enabled      BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (workspace_id, provider, model)
);

CREATE INDEX workspace_llm_configs_ws ON workspace_llm_configs (workspace_id);
```

- [ ] **Ajouter les dépendances dans `pyproject.toml`**

Dans le bloc `dependencies`, ajouter après `"pyyaml>=6.0.3",` :

```toml
    "anthropic>=0.40",
    "openai>=1.50",
```

- [ ] **Synchroniser**

```bash
cd backend && uv sync
```

- [ ] **Commit**

```bash
git add backend/migrations/030_workspace_llm_configs.sql backend/pyproject.toml
git commit -m "feat(db): migration 030 workspace_llm_configs + deps anthropic+openai"
```

---

## Task 2 : Schemas playground.py

**Files:**
- Create: `backend/src/rag/schemas/playground.py`

- [ ] **Créer `backend/src/rag/schemas/playground.py`**

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

LlmProvider = Literal["claude", "openai", "azure-openai", "ollama"]


class LlmConfigCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    provider: LlmProvider
    model: str = Field(min_length=1, max_length=128)
    base_url: str | None = None
    api_key_ref: str | None = None
    enabled: bool = True


class LlmConfigPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class LlmConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: str
    model: str
    base_url: str | None
    api_key_ref: str | None
    enabled: bool
    created_at: datetime


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatLlmSpec(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    provider: str
    model: str


class PlaygroundChatRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    llm: ChatLlmSpec
    top_k: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.7, ge=0.0, le=1.0)


class ChunkResult(BaseModel):
    path: str
    chunk_index: int
    content: str
    score: float


class UsageInfo(BaseModel):
    prompt_tokens: int
    completion_tokens: int


class PlaygroundChatResponse(BaseModel):
    message: str
    answer: str
    chunks: list[ChunkResult]
    usage: UsageInfo
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/schemas/playground.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/schemas/playground.py
git commit -m "feat(schemas): playground — LlmConfig + PlaygroundChat DTOs"
```

---

## Task 3 : Service llm_configs.py

**Files:**
- Create: `backend/src/rag/services/llm_configs.py`

- [ ] **Créer `backend/src/rag/services/llm_configs.py`**

```python
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
import structlog

from rag.schemas.playground import LlmConfigCreate, LlmConfigOut, LlmConfigPatch

log = structlog.get_logger(__name__)


async def list_llm_configs(
    conn: asyncpg.Connection, *, workspace_name: str
) -> list[LlmConfigOut]:
    rows = await conn.fetch(
        """
        SELECT lc.id, lc.provider, lc.model, lc.base_url, lc.api_key_ref,
               lc.enabled, lc.created_at
        FROM workspace_llm_configs lc
        JOIN workspaces w ON w.id = lc.workspace_id
        WHERE w.name = $1
        ORDER BY lc.provider, lc.model
        """,
        workspace_name,
    )
    return [LlmConfigOut.model_validate(dict(r)) for r in rows]


async def create_llm_config(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    req: LlmConfigCreate,
) -> LlmConfigOut:
    row = await conn.fetchrow(
        """
        INSERT INTO workspace_llm_configs
            (workspace_id, provider, model, base_url, api_key_ref, enabled)
        SELECT w.id, $2, $3, $4, $5, $6
        FROM workspaces w WHERE w.name = $1
        RETURNING id, provider, model, base_url, api_key_ref, enabled, created_at
        """,
        workspace_name,
        req.provider,
        req.model,
        req.base_url,
        req.api_key_ref,
        req.enabled,
    )
    if row is None:
        raise ValueError(f"workspace {workspace_name!r} not found")
    log.info("llm_config.created", workspace=workspace_name, provider=req.provider, model=req.model)
    return LlmConfigOut.model_validate(dict(row))


async def patch_llm_config(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    config_id: str,
    req: LlmConfigPatch,
) -> LlmConfigOut | None:
    row = await conn.fetchrow(
        """
        UPDATE workspace_llm_configs lc
        SET enabled = $3
        FROM workspaces w
        WHERE w.id = lc.workspace_id AND w.name = $1 AND lc.id = $2::uuid
        RETURNING lc.id, lc.provider, lc.model, lc.base_url,
                  lc.api_key_ref, lc.enabled, lc.created_at
        """,
        workspace_name,
        config_id,
        req.enabled,
    )
    return LlmConfigOut.model_validate(dict(row)) if row else None


async def delete_llm_config(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    config_id: str,
) -> bool:
    result = await conn.execute(
        """
        DELETE FROM workspace_llm_configs lc
        USING workspaces w
        WHERE w.id = lc.workspace_id AND w.name = $1 AND lc.id = $2::uuid
        """,
        workspace_name,
        config_id,
    )
    return result != "DELETE 0"


async def get_llm_config_for_chat(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    provider: str,
    model: str,
) -> dict[str, Any] | None:
    """Retourne la config LLM enabled pour (workspace, provider, model)."""
    row = await conn.fetchrow(
        """
        SELECT lc.provider, lc.model, lc.base_url, lc.api_key_ref
        FROM workspace_llm_configs lc
        JOIN workspaces w ON w.id = lc.workspace_id
        WHERE w.name = $1 AND lc.provider = $2 AND lc.model = $3 AND lc.enabled = true
        """,
        workspace_name,
        provider,
        model,
    )
    return dict(row) if row else None
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/services/llm_configs.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/services/llm_configs.py
git commit -m "feat(services): CRUD workspace_llm_configs"
```

---

## Task 4 : Service llm_clients.py (TDD)

**Files:**
- Create: `backend/src/rag/services/llm_clients.py`
- Create: `backend/tests/unit/test_llm_clients.py`

- [ ] **Écrire les tests (rouge)**

```python
# backend/tests/unit/test_llm_clients.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag.services.llm_clients import build_prompt, call_llm


def test_build_prompt_includes_context_and_history() -> None:
    chunks = [
        {"path": "doc/a.md", "content": "Le gap handling utilise sync_shelf.", "score": 0.9},
    ]
    history = [
        {"role": "user", "content": "explique la réplication"},
        {"role": "assistant", "content": "La réplication repose sur MQTT."},
    ]
    system, messages = build_prompt(
        chunks=chunks,
        history=history,
        message="et le gap handling ?",
    )
    assert "sync_shelf" in system
    assert "doc/a.md" in system
    assert len(messages) == 3  # history (2) + message courant (1)
    assert messages[-1]["role"] == "user"
    assert "gap handling" in messages[-1]["content"]


def test_build_prompt_no_chunks_signals_no_context() -> None:
    system, messages = build_prompt(chunks=[], history=[], message="question ?")
    assert "aucun" in system.lower() or "no" in system.lower() or "context" in system.lower()


@pytest.mark.asyncio
async def test_call_llm_claude_returns_answer() -> None:
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Réponse Claude.")]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("rag.services.llm_clients.anthropic") as mock_anthropic:
        mock_anthropic.AsyncAnthropic.return_value = mock_client
        result = await call_llm(
            provider="claude",
            model="claude-sonnet-4-5",
            api_key="sk-ant-test",
            base_url=None,
            system_prompt="You are helpful.",
            messages=[{"role": "user", "content": "hello"}],
        )

    assert result["answer"] == "Réponse Claude."
    assert result["usage"]["prompt_tokens"] == 100
    assert result["usage"]["completion_tokens"] == 50


@pytest.mark.asyncio
async def test_call_llm_openai_returns_answer() -> None:
    mock_choice = MagicMock()
    mock_choice.message.content = "Réponse OpenAI."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 80
    mock_response.usage.completion_tokens = 40

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("rag.services.llm_clients.openai") as mock_openai:
        mock_openai.AsyncOpenAI.return_value = mock_client
        result = await call_llm(
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
            base_url=None,
            system_prompt="You are helpful.",
            messages=[{"role": "user", "content": "hello"}],
        )

    assert result["answer"] == "Réponse OpenAI."
    assert result["usage"]["prompt_tokens"] == 80
```

- [ ] **Créer `backend/src/rag/services/llm_clients.py`**

```python
from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]


_SYSTEM_TEMPLATE = """\
Tu es un assistant expert. Réponds en te basant uniquement sur le contexte fourni.
Si la réponse n'est pas dans le contexte, dis-le explicitement.

[Contexte RAG]
---
{context}
---
"""

_SYSTEM_NO_CONTEXT = """\
Tu es un assistant expert. Aucun contexte pertinent n'a été trouvé dans le corpus.
Dis-le explicitement à l'utilisateur.
"""


def build_prompt(
    *,
    chunks: list[dict[str, Any]],
    history: list[dict[str, str]],
    message: str,
) -> tuple[str, list[dict[str, str]]]:
    """Construit le system prompt + la liste de messages pour le LLM.

    Retourne (system_prompt, messages) où messages = history + message courant.
    """
    if chunks:
        context_parts = [
            f"[chunk — path: {c['path']}]\n{c['content']}"
            for c in chunks
        ]
        system = _SYSTEM_TEMPLATE.format(context="\n\n".join(context_parts))
    else:
        system = _SYSTEM_NO_CONTEXT

    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in history
    ]
    messages.append({"role": "user", "content": message})
    return system, messages


async def call_llm(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
    system_prompt: str,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    """Appelle le LLM et retourne {answer, usage: {prompt_tokens, completion_tokens}}.

    Supporte : claude, openai, azure-openai, ollama.
    """
    if provider == "claude":
        return await _call_claude(
            model=model, api_key=api_key, system=system_prompt, messages=messages
        )
    if provider == "openai":
        return await _call_openai(
            model=model, api_key=api_key, system=system_prompt, messages=messages
        )
    if provider == "azure-openai":
        return await _call_azure_openai(
            model=model, api_key=api_key, base_url=base_url,
            system=system_prompt, messages=messages,
        )
    if provider == "ollama":
        return await _call_ollama(
            model=model, base_url=base_url or "http://localhost:11434",
            system=system_prompt, messages=messages,
        )
    raise ValueError(f"Unsupported LLM provider: {provider!r}")


async def _call_claude(
    *,
    model: str,
    api_key: str | None,
    system: str,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    client = anthropic.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=model,
        max_tokens=2000,
        system=system,
        messages=messages,
    )
    return {
        "answer": response.content[0].text,
        "usage": {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
        },
    }


async def _call_openai(
    *,
    model: str,
    api_key: str | None,
    system: str,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    client = openai.AsyncOpenAI(api_key=api_key)
    full_messages = [{"role": "system", "content": system}, *messages]
    response = await client.chat.completions.create(model=model, messages=full_messages)
    return {
        "answer": response.choices[0].message.content or "",
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        },
    }


async def _call_azure_openai(
    *,
    model: str,
    api_key: str | None,
    base_url: str | None,
    system: str,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    client = openai.AsyncAzureOpenAI(
        api_key=api_key,
        azure_endpoint=base_url or "",
        api_version="2024-02-01",
    )
    full_messages = [{"role": "system", "content": system}, *messages]
    response = await client.chat.completions.create(model=model, messages=full_messages)
    return {
        "answer": response.choices[0].message.content or "",
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        },
    }


async def _call_ollama(
    *,
    model: str,
    base_url: str,
    system: str,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    full_messages = [{"role": "system", "content": system}, *messages]
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/api/chat",
            json={"model": model, "messages": full_messages, "stream": False},
        )
        response.raise_for_status()
        data = response.json()
    return {
        "answer": data["message"]["content"],
        "usage": {
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "completion_tokens": data.get("eval_count", 0),
        },
    }
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_llm_clients.py -v
```

Résultat attendu : 4 tests PASS.

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/services/llm_clients.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/services/llm_clients.py backend/tests/unit/test_llm_clients.py
git commit -m "feat(services): llm_clients — Claude/OpenAI/Azure/Ollama + build_prompt"
```

---

## Task 5 : Router playground.py + main.py

**Files:**
- Create: `backend/src/rag/api/playground.py`
- Modify: `backend/src/rag/main.py`

- [ ] **Créer `backend/src/rag/api/playground.py`**

```python
from __future__ import annotations

from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.auth.bearer import require_master_key_or_oidc_role
from rag.schemas.playground import (
    LlmConfigCreate,
    LlmConfigOut,
    LlmConfigPatch,
    PlaygroundChatRequest,
    PlaygroundChatResponse,
)

log = structlog.get_logger(__name__)

# ─── CRUD LLM configs (admin) ────────────────────────────────────────────────

router_admin = APIRouter(
    prefix="/api/admin/workspaces/{workspace_name}/llm-configs",
    tags=["playground-admin"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


def _pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pools.config_pool  # type: ignore[no-any-return]


@router_admin.get("", response_model=list[LlmConfigOut])
async def list_configs(workspace_name: str, request: Request) -> list[LlmConfigOut]:
    from rag.services.llm_configs import list_llm_configs
    async with _pool(request).acquire() as conn:
        return await list_llm_configs(conn, workspace_name=workspace_name)


@router_admin.post("", response_model=LlmConfigOut, status_code=201)
async def create_config(
    workspace_name: str, body: LlmConfigCreate, request: Request
) -> LlmConfigOut:
    from rag.services.llm_configs import create_llm_config
    async with _pool(request).acquire() as conn:
        try:
            return await create_llm_config(conn, workspace_name=workspace_name, req=body)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise HTTPException(status.HTTP_409_CONFLICT, "already exists") from exc
            raise


@router_admin.patch("/{config_id}", response_model=LlmConfigOut)
async def patch_config(
    workspace_name: str, config_id: UUID, body: LlmConfigPatch, request: Request
) -> LlmConfigOut:
    from rag.services.llm_configs import patch_llm_config
    async with _pool(request).acquire() as conn:
        result = await patch_llm_config(
            conn, workspace_name=workspace_name, config_id=str(config_id), req=body
        )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "llm config not found")
    return result


@router_admin.delete("/{config_id}", status_code=204)
async def delete_config(
    workspace_name: str, config_id: UUID, request: Request
) -> Response:
    from rag.services.llm_configs import delete_llm_config
    async with _pool(request).acquire() as conn:
        deleted = await delete_llm_config(
            conn, workspace_name=workspace_name, config_id=str(config_id)
        )
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "llm config not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Chat (rag-admin + rag-viewer) ───────────────────────────────────────────

router_chat = APIRouter(
    prefix="/api/workspaces",
    tags=["playground-chat"],
    dependencies=[Depends(require_master_key_or_oidc_role("rag-viewer"))],
)


@router_chat.post("/{workspace_name}/playground/chat", response_model=PlaygroundChatResponse)
async def playground_chat(
    workspace_name: str,
    body: PlaygroundChatRequest,
    request: Request,
) -> PlaygroundChatResponse:
    """Chat RAG-ancré : embed → search → LLM."""
    from rag.db.workspace_search import vector_search
    from rag.indexer.providers.factory import make_provider
    from rag.secrets.refs import is_vault_ref, parse_ref
    from rag.services.llm_clients import build_prompt, call_llm
    from rag.services.llm_configs import get_llm_config_for_chat

    config_pool: asyncpg.Pool = _pool(request)
    pool_registry = request.app.state.pool_registry
    vault_svc = request.app.state.harpocrate_vaults_service
    client_provider = request.app.state.client_provider

    async def _resolve_harpo(harpo_path: str) -> str | None:
        """Résout un harpo_path (vault_name-based) → valeur secrète."""
        if not is_vault_ref(harpo_path):
            return None
        vault_name, secret_path = parse_ref(harpo_path)
        async with config_pool.acquire() as conn:
            vault = await vault_svc.get_by_name(conn, vault_name)
        if vault is None:
            return None
        client = await client_provider.get_client(vault.api_key_id)
        import asyncio
        return await asyncio.to_thread(client.get_secret, secret_path)

    # 1. Charger le workspace + indexer config
    async with config_pool.acquire() as conn:
        ws_row = await conn.fetchrow(
            """
            SELECT w.rag_cnx, w.name AS ws_name,
                   ic.provider AS idx_provider, ic.model AS idx_model,
                   ic.api_key_ref AS idx_api_key_ref, ic.base_url AS idx_base_url
            FROM workspaces w
            JOIN indexer_configs ic ON ic.workspace_id = w.id
            WHERE w.name = $1
            """,
            workspace_name,
        )
        if ws_row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "workspace not found")

        # 2. Charger la config LLM
        llm_cfg = await get_llm_config_for_chat(
            conn,
            workspace_name=workspace_name,
            provider=body.llm.provider,
            model=body.llm.model,
        )
    if llm_cfg is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"LLM {body.llm.provider}/{body.llm.model} not configured or disabled",
        )

    # 3. Résoudre la clé indexer et embed la requête
    indexer_api_key: str | None = None
    if ws_row["idx_api_key_ref"]:
        indexer_api_key = await _resolve_harpo(ws_row["idx_api_key_ref"])

    embedding_provider = make_provider(
        provider=ws_row["idx_provider"],
        model=ws_row["idx_model"],
        api_key=indexer_api_key,
        base_url=ws_row["idx_base_url"],
    )
    query_vec = await embedding_provider.embed_query(body.message)

    # 4. Recherche vectorielle
    ws_pool = await pool_registry.get_workspace_pool(workspace_name, ws_row["rag_cnx"])
    raw_hits = await vector_search(
        ws_pool,
        query_vec=query_vec,
        top_k=body.top_k,
        min_score=body.min_score,
        workspace_name=workspace_name,
        indexer_used=f"{ws_row['idx_provider']}/{ws_row['idx_model']}",
    )

    chunks = [
        {"path": h.path, "chunk_index": h.chunk_index, "content": h.content, "score": h.score}
        for h in raw_hits
    ]

    # 5. Appel LLM
    llm_api_key: str | None = None
    if llm_cfg.get("api_key_ref"):
        llm_api_key = await _resolve_harpo(llm_cfg["api_key_ref"])

    system_prompt, messages = build_prompt(
        chunks=chunks,
        history=[{"role": m.role, "content": m.content} for m in body.history],
        message=body.message,
    )
    llm_result = await call_llm(
        provider=llm_cfg["provider"],
        model=llm_cfg["model"],
        api_key=llm_api_key,
        base_url=llm_cfg.get("base_url"),
        system_prompt=system_prompt,
        messages=messages,
    )

    log.info(
        "playground.chat",
        workspace=workspace_name,
        provider=llm_cfg["provider"],
        model=llm_cfg["model"],
        chunks=len(chunks),
        tokens=llm_result["usage"],
    )

    return PlaygroundChatResponse(
        message=body.message,
        answer=llm_result["answer"],
        chunks=[
            {"path": c["path"], "chunk_index": c["chunk_index"],
             "content": c["content"], "score": c["score"]}
            for c in chunks
        ],
        usage=llm_result["usage"],
    )
```

- [ ] **Enregistrer dans `main.py`**

Après les imports existants des routers, ajouter :

```python
from rag.api.playground import router_admin as playground_admin_router
from rag.api.playground import router_chat as playground_chat_router
```

Après les `app.include_router` existants :

```python
app.include_router(playground_admin_router)
app.include_router(playground_chat_router)
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/api/playground.py src/rag/main.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/api/playground.py backend/src/rag/main.py
git commit -m "feat(api): playground — CRUD LLM configs + POST /playground/chat"
```

---

## Task 6 : Frontend — types + API client + hooks + i18n

**Files:**
- Create: `frontend/src/lib/playground.types.ts`
- Create: `frontend/src/lib/playground.ts`
- Create: `frontend/src/hooks/usePlayground.ts`
- Create: `frontend/src/i18n/fr/playground.json`
- Create: `frontend/src/i18n/en/playground.json`
- Modify: `frontend/src/i18n/fr/workspace.json`
- Modify: `frontend/src/i18n/en/workspace.json`

- [ ] **Créer `frontend/src/lib/playground.types.ts`**

```typescript
export type LlmProvider = "claude" | "openai" | "azure-openai" | "ollama";

export type LlmConfig = {
  id: string;
  provider: LlmProvider;
  model: string;
  base_url: string | null;
  api_key_ref: string | null;
  enabled: boolean;
  created_at: string;
};

export type LlmConfigCreate = {
  provider: LlmProvider;
  model: string;
  base_url?: string | null;
  api_key_ref?: string | null;
  enabled?: boolean;
};

export type LlmConfigPatch = {
  enabled: boolean;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type ChunkResult = {
  path: string;
  chunk_index: number;
  content: string;
  score: number;
};

export type PlaygroundChatRequest = {
  message: string;
  history: ChatMessage[];
  llm: { provider: string; model: string };
  top_k?: number;
  min_score?: number;
};

export type PlaygroundChatResponse = {
  message: string;
  answer: string;
  chunks: ChunkResult[];
  usage: { prompt_tokens: number; completion_tokens: number };
};
```

- [ ] **Créer `frontend/src/lib/playground.ts`**

```typescript
import { api } from "@/lib/api";
import type {
  LlmConfig,
  LlmConfigCreate,
  LlmConfigPatch,
  PlaygroundChatRequest,
  PlaygroundChatResponse,
} from "@/lib/playground.types";

const BASE = (name: string) => `/api/admin/workspaces/${name}/llm-configs`;

export const playgroundApi = {
  listConfigs: (workspaceName: string) =>
    api.get<LlmConfig[]>(BASE(workspaceName)),

  createConfig: (workspaceName: string, payload: LlmConfigCreate) =>
    api.post<LlmConfig>(BASE(workspaceName), payload),

  patchConfig: (workspaceName: string, configId: string, payload: LlmConfigPatch) =>
    api.patch<LlmConfig>(`${BASE(workspaceName)}/${configId}`, payload),

  deleteConfig: (workspaceName: string, configId: string) =>
    api.delete<void>(`${BASE(workspaceName)}/${configId}`),

  chat: (workspaceName: string, payload: PlaygroundChatRequest) =>
    api.post<PlaygroundChatResponse>(
      `/api/workspaces/${workspaceName}/playground/chat`,
      payload,
    ),
};
```

- [ ] **Créer `frontend/src/hooks/usePlayground.ts`**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { playgroundApi } from "@/lib/playground";
import type { LlmConfigCreate, LlmConfigPatch, PlaygroundChatRequest } from "@/lib/playground.types";

const ROOT = (name: string) => ["playground", name, "llm-configs"] as const;

export function useLlmConfigs(workspaceName: string) {
  return useQuery({
    queryKey: ROOT(workspaceName),
    queryFn: () => playgroundApi.listConfigs(workspaceName),
    staleTime: 30_000,
  });
}

export function useAddLlmConfig(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: LlmConfigCreate) =>
      playgroundApi.createConfig(workspaceName, payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ROOT(workspaceName) }),
  });
}

export function usePatchLlmConfig(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ configId, payload }: { configId: string; payload: LlmConfigPatch }) =>
      playgroundApi.patchConfig(workspaceName, configId, payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ROOT(workspaceName) }),
  });
}

export function useDeleteLlmConfig(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (configId: string) => playgroundApi.deleteConfig(workspaceName, configId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ROOT(workspaceName) }),
  });
}

export function usePlaygroundChat(workspaceName: string) {
  return useMutation({
    mutationFn: (payload: PlaygroundChatRequest) =>
      playgroundApi.chat(workspaceName, payload),
  });
}
```

- [ ] **Créer `frontend/src/i18n/fr/playground.json`**

```json
{
  "tabs": {
    "config": "Config LLM",
    "chat": "Chat"
  },
  "config": {
    "title": "Configurations LLM",
    "add_btn": "Ajouter un LLM",
    "empty": "Aucun LLM configuré pour ce workspace.",
    "col_provider": "Provider",
    "col_model": "Modèle",
    "col_key": "Clé API",
    "col_enabled": "Activé",
    "delete_btn": "Supprimer",
    "delete_confirm_title": "Supprimer cette config LLM ?",
    "delete_confirm_body": "Cette configuration sera supprimée. Irréversible.",
    "deleted_toast": "Config LLM supprimée.",
    "add_dialog_title": "Ajouter un LLM",
    "field_provider": "Provider",
    "field_model": "Modèle",
    "field_key": "Clé API",
    "field_key_none": "Aucune clé disponible pour ce provider",
    "field_base_url": "Base URL",
    "field_base_url_placeholder": "http://localhost:11434",
    "save": "Ajouter",
    "cancel": "Annuler",
    "error_toast": "Erreur lors de la configuration.",
    "error_duplicate": "Ce modèle est déjà configuré."
  },
  "chat": {
    "placeholder": "Votre message...",
    "send": "Envoyer",
    "reset": "Réinitialiser",
    "llm_label": "LLM",
    "top_k_label": "top_k",
    "min_score_label": "score min",
    "no_llm": "Aucun LLM activé — configurez d'abord un LLM dans l'onglet Config.",
    "chunks_toggle": "Chunks utilisés ({{count}})",
    "tokens": "Tokens : prompt={{prompt}} / completion={{completion}}",
    "thinking": "Réflexion en cours…",
    "error_toast": "Erreur lors de l'appel LLM."
  }
}
```

- [ ] **Créer `frontend/src/i18n/en/playground.json`**

```json
{
  "tabs": {
    "config": "LLM Config",
    "chat": "Chat"
  },
  "config": {
    "title": "LLM Configurations",
    "add_btn": "Add LLM",
    "empty": "No LLM configured for this workspace.",
    "col_provider": "Provider",
    "col_model": "Model",
    "col_key": "API Key",
    "col_enabled": "Enabled",
    "delete_btn": "Delete",
    "delete_confirm_title": "Delete this LLM config?",
    "delete_confirm_body": "This configuration will be deleted. Irreversible.",
    "deleted_toast": "LLM config deleted.",
    "add_dialog_title": "Add LLM",
    "field_provider": "Provider",
    "field_model": "Model",
    "field_key": "API Key",
    "field_key_none": "No key available for this provider",
    "field_base_url": "Base URL",
    "field_base_url_placeholder": "http://localhost:11434",
    "save": "Add",
    "cancel": "Cancel",
    "error_toast": "Configuration error.",
    "error_duplicate": "This model is already configured."
  },
  "chat": {
    "placeholder": "Your message...",
    "send": "Send",
    "reset": "Reset",
    "llm_label": "LLM",
    "top_k_label": "top_k",
    "min_score_label": "min score",
    "no_llm": "No LLM enabled — configure one in the Config tab first.",
    "chunks_toggle": "Used chunks ({{count}})",
    "tokens": "Tokens: prompt={{prompt}} / completion={{completion}}",
    "thinking": "Thinking…",
    "error_toast": "LLM call failed."
  }
}
```

- [ ] **Ajouter `tabs.playground` dans les fichiers i18n workspace**

Dans `frontend/src/i18n/fr/workspace.json`, dans l'objet `tabs`, ajouter :
```json
"playground": "Playground"
```

Dans `frontend/src/i18n/en/workspace.json` :
```json
"playground": "Playground"
```

- [ ] **Enregistrer le namespace playground dans i18n**

Lis `frontend/src/lib/i18n.ts` (ou le fichier d'init i18n). Ajouter `playground` dans les namespaces chargés.

- [ ] **Vérifier TypeScript + JSON**

```bash
cd frontend && npx tsc --noEmit
node -e "JSON.parse(require('fs').readFileSync('src/i18n/fr/playground.json','utf8')); console.log('OK')"
```

- [ ] **Commit**

```bash
git add frontend/src/lib/playground.types.ts \
        frontend/src/lib/playground.ts \
        frontend/src/hooks/usePlayground.ts \
        frontend/src/i18n/fr/playground.json \
        frontend/src/i18n/en/playground.json \
        frontend/src/i18n/fr/workspace.json \
        frontend/src/i18n/en/workspace.json
git commit -m "feat(front): playground types + API client + hooks + i18n"
```

---

## Task 7 : AddLlmConfigDialog.tsx

**Files:**
- Create: `frontend/src/pages/workspace/AddLlmConfigDialog.tsx`

- [ ] **Créer `frontend/src/pages/workspace/AddLlmConfigDialog.tsx`**

```tsx
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { useAddLlmConfig } from "@/hooks/usePlayground";
import { useProviderKeysByProvider } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";
import type { LlmProvider } from "@/lib/playground.types";

const PROVIDERS: { value: LlmProvider; label: string }[] = [
  { value: "claude", label: "Claude (Anthropic)" },
  { value: "openai", label: "OpenAI" },
  { value: "azure-openai", label: "Azure OpenAI" },
  { value: "ollama", label: "Ollama (local)" },
];

const MODELS_BY_PROVIDER: Record<LlmProvider, string[]> = {
  claude: ["claude-sonnet-4-5", "claude-opus-4-5"],
  openai: ["gpt-4o", "gpt-4o-mini", "o1"],
  "azure-openai": ["gpt-4o", "gpt-4o-mini"],
  ollama: [],
};

const NEEDS_BASE_URL: LlmProvider[] = ["azure-openai", "ollama"];
const NO_KEY_PROVIDERS: LlmProvider[] = ["ollama"];

interface Props {
  workspaceName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddLlmConfigDialog({ workspaceName, open, onOpenChange }: Props) {
  const { t } = useTranslation("playground");
  const { toast } = useToast();
  const mutation = useAddLlmConfig(workspaceName);

  const [provider, setProvider] = useState<LlmProvider | "">("");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [ollamaModel, setOllamaModel] = useState("");

  const needsKey = provider && !NO_KEY_PROVIDERS.includes(provider as LlmProvider);
  const needsBaseUrl = provider && NEEDS_BASE_URL.includes(provider as LlmProvider);
  const { data: keys = [] } = useProviderKeysByProvider(needsKey ? provider : null);

  const [selectedKey, setSelectedKey] = useState("");

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setProvider(""); setModel(""); setBaseUrl(""); setSelectedKey(""); setOllamaModel("");
    }
  }

  const effectiveModel = provider === "ollama" ? ollamaModel : model;
  const canSubmit =
    !!provider && !!effectiveModel && !mutation.isPending &&
    (!needsBaseUrl || !!baseUrl) &&
    (!needsKey || keys.length === 0 || !!selectedKey);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit || !provider) return;
    try {
      await mutation.mutateAsync({
        provider: provider as LlmProvider,
        model: effectiveModel,
        base_url: baseUrl || null,
        api_key_ref: selectedKey || null,
        enabled: true,
      });
      handleClose(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("config.error_duplicate"), variant: "destructive" });
      } else {
        toast({ title: t("config.error_toast"), variant: "destructive" });
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("config.add_dialog_title")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("config.field_provider")}
            </Label>
            <Select value={provider} onValueChange={(v) => { setProvider(v as LlmProvider); setModel(""); setSelectedKey(""); }}>
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="Claude, OpenAI…" />
              </SelectTrigger>
              <SelectContent>
                {PROVIDERS.map((p) => (
                  <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {provider && provider !== "ollama" && (
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("config.field_model")}
              </Label>
              <Select value={model} onValueChange={setModel}>
                <SelectTrigger className="mt-1 font-mono">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MODELS_BY_PROVIDER[provider as LlmProvider].map((m) => (
                    <SelectItem key={m} value={m} className="font-mono">{m}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {provider === "ollama" && (
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("config.field_model")}
              </Label>
              <Input
                value={ollamaModel}
                onChange={(e) => setOllamaModel(e.target.value)}
                placeholder="llama3, mistral…"
                className="mt-1 font-mono"
              />
            </div>
          )}

          {needsBaseUrl && (
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("config.field_base_url")}
              </Label>
              <Input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder={t("config.field_base_url_placeholder")}
                className="mt-1 font-mono"
              />
            </div>
          )}

          {needsKey && (
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("config.field_key")}
              </Label>
              {keys.length === 0 ? (
                <p className="text-xs text-amber-600 mt-1">{t("config.field_key_none")}</p>
              ) : (
                <Select value={selectedKey} onValueChange={setSelectedKey}>
                  <SelectTrigger className="mt-1">
                    <SelectValue placeholder="Sélectionner une clé…" />
                  </SelectTrigger>
                  <SelectContent>
                    {keys.map((k) => (
                      <SelectItem key={k.id} value={k.harpo_path}>
                        <span className="font-medium">{k.label}</span>
                        <span className="ml-2 text-xs text-slate-400">{k.vault_label} · {k.key_id}</span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              {t("config.cancel")}
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {t("config.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Vérifier TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Commit**

```bash
git add frontend/src/pages/workspace/AddLlmConfigDialog.tsx
git commit -m "feat(front): AddLlmConfigDialog"
```

---

## Task 8 : PlaygroundLlmConfigTab + PlaygroundChatTab

**Files:**
- Create: `frontend/src/pages/workspace/PlaygroundLlmConfigTab.tsx`
- Create: `frontend/src/pages/workspace/PlaygroundChatTab.tsx`

- [ ] **Créer `frontend/src/pages/workspace/PlaygroundLlmConfigTab.tsx`**

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useLlmConfigs, useDeleteLlmConfig, usePatchLlmConfig } from "@/hooks/usePlayground";
import { useToast } from "@/hooks/useToast";
import { AddLlmConfigDialog } from "./AddLlmConfigDialog";
import type { LlmConfig } from "@/lib/playground.types";

interface Props {
  workspaceName: string;
}

export function PlaygroundLlmConfigTab({ workspaceName }: Props) {
  const { t } = useTranslation("playground");
  const { toast } = useToast();
  const { data: configs = [], isLoading } = useLlmConfigs(workspaceName);
  const deleteMutation = useDeleteLlmConfig(workspaceName);
  const patchMutation = usePatchLlmConfig(workspaceName);
  const [addOpen, setAddOpen] = useState(false);
  const [toDelete, setToDelete] = useState<LlmConfig | null>(null);

  async function handleDelete() {
    if (!toDelete) return;
    try {
      await deleteMutation.mutateAsync(toDelete.id);
      toast({ title: t("config.deleted_toast") });
    } catch {
      toast({ title: t("config.error_toast"), variant: "destructive" });
    } finally {
      setToDelete(null);
    }
  }

  async function handleToggle(cfg: LlmConfig) {
    await patchMutation.mutateAsync({ configId: cfg.id, payload: { enabled: !cfg.enabled } });
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setAddOpen(true)}>
          {t("config.add_btn")}
        </Button>
      </div>

      {!isLoading && configs.length === 0 ? (
        <div className="rounded border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("config.empty")}
        </div>
      ) : (
        <div className="overflow-hidden rounded border border-slate-200">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("config.col_provider")}</TableHead>
                <TableHead>{t("config.col_model")}</TableHead>
                <TableHead>{t("config.col_key")}</TableHead>
                <TableHead>{t("config.col_enabled")}</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {configs.map((cfg) => (
                <TableRow key={cfg.id}>
                  <TableCell>
                    <span className="rounded bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700">
                      {cfg.provider}
                    </span>
                  </TableCell>
                  <TableCell className="font-mono text-sm">{cfg.model}</TableCell>
                  <TableCell className="text-xs text-slate-400">
                    {cfg.api_key_ref ? cfg.api_key_ref.split("/").pop() ?? "—" : "—"}
                  </TableCell>
                  <TableCell>
                    <Switch
                      checked={cfg.enabled}
                      onCheckedChange={() => handleToggle(cfg)}
                      disabled={patchMutation.isPending}
                    />
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setToDelete(cfg)}
                      className="text-rose-600 hover:text-rose-700"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <AddLlmConfigDialog
        workspaceName={workspaceName}
        open={addOpen}
        onOpenChange={setAddOpen}
      />

      <AlertDialog open={!!toDelete} onOpenChange={(o) => { if (!o) setToDelete(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("config.delete_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>{t("config.delete_confirm_body")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("config.cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-rose-600 hover:bg-rose-700">
              {t("config.delete_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
```

- [ ] **Créer `frontend/src/pages/workspace/PlaygroundChatTab.tsx`**

```tsx
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Send, RotateCcw, ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { useLlmConfigs, usePlaygroundChat } from "@/hooks/usePlayground";
import { useToast } from "@/hooks/useToast";
import type { ChatMessage, ChunkResult, PlaygroundChatResponse } from "@/lib/playground.types";

interface ConversationTurn {
  question: string;
  response: PlaygroundChatResponse;
}

interface Props {
  workspaceName: string;
}

function ChunksCollapsible({ chunks }: { chunks: ChunkResult[] }) {
  const { t } = useTranslation("playground");
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button
        type="button"
        className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700"
        onClick={() => setOpen(!open)}
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        {t("chat.chunks_toggle", { count: chunks.length })}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {chunks.map((c, i) => (
            <div key={i} className="rounded bg-slate-50 border border-slate-200 p-2 text-xs">
              <div className="flex justify-between text-slate-500 mb-1">
                <span className="font-mono">{c.path}</span>
                <span className="text-emerald-600 font-medium">score {c.score.toFixed(3)}</span>
              </div>
              <p className="text-slate-700 line-clamp-3">{c.content}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function PlaygroundChatTab({ workspaceName }: Props) {
  const { t } = useTranslation("playground");
  const { toast } = useToast();
  const { data: configs = [] } = useLlmConfigs(workspaceName);
  const chatMutation = usePlaygroundChat(workspaceName);

  const enabledConfigs = configs.filter((c) => c.enabled);

  const [selectedLlm, setSelectedLlm] = useState("");
  const [topK, setTopK] = useState(5);
  const [minScore, setMinScore] = useState(0.7);
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  function handleReset() {
    setHistory([]);
    setTurns([]);
    setInput("");
  }

  async function handleSend() {
    if (!input.trim() || !selectedLlm || chatMutation.isPending) return;
    const [provider, ...modelParts] = selectedLlm.split("/");
    const model = modelParts.join("/");
    const message = input.trim();
    setInput("");

    try {
      const response = await chatMutation.mutateAsync({
        message,
        history,
        llm: { provider, model },
        top_k: topK,
        min_score: minScore,
      });
      setTurns((prev) => [...prev, { question: message, response }]);
      setHistory((prev) => [
        ...prev,
        { role: "user", content: message },
        { role: "assistant", content: response.answer },
      ]);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    } catch {
      toast({ title: t("chat.error_toast"), variant: "destructive" });
    }
  }

  if (enabledConfigs.length === 0) {
    return (
      <div className="rounded border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
        {t("chat.no_llm")}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[600px]">
      {/* Barre de config */}
      <div className="flex items-center gap-3 pb-3 border-b border-slate-200">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">{t("chat.llm_label")}</span>
          <Select value={selectedLlm} onValueChange={setSelectedLlm}>
            <SelectTrigger className="w-56 h-8 text-xs">
              <SelectValue placeholder="Sélectionner…" />
            </SelectTrigger>
            <SelectContent>
              {enabledConfigs.map((c) => (
                <SelectItem key={c.id} value={`${c.provider}/${c.model}`} className="text-xs font-mono">
                  {c.provider} / {c.model}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-xs text-slate-500">{t("chat.top_k_label")}</span>
          <Input
            type="number"
            min={1}
            max={50}
            value={topK}
            onChange={(e) => setTopK(parseInt(e.target.value, 10) || 5)}
            className="w-16 h-8 text-xs"
          />
        </div>
        <div className="flex items-center gap-1">
          <span className="text-xs text-slate-500">{t("chat.min_score_label")}</span>
          <Input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={minScore}
            onChange={(e) => setMinScore(parseFloat(e.target.value) || 0.7)}
            className="w-16 h-8 text-xs"
          />
        </div>
        <Button variant="ghost" size="sm" onClick={handleReset} className="ml-auto">
          <RotateCcw className="h-3.5 w-3.5 mr-1" />
          {t("chat.reset")}
        </Button>
      </div>

      {/* Historique */}
      <div className="flex-1 overflow-y-auto py-3 space-y-4">
        {turns.map((turn, i) => (
          <div key={i} className="space-y-2">
            <div className="flex justify-end">
              <div className="max-w-[80%] rounded-lg bg-blue-600 text-white px-3 py-2 text-sm">
                {turn.question}
              </div>
            </div>
            <div className="max-w-[85%]">
              <div className="rounded-lg bg-slate-100 px-3 py-2 text-sm whitespace-pre-wrap">
                {turn.response.answer}
              </div>
              <ChunksCollapsible chunks={turn.response.chunks} />
              <p className="text-xs text-slate-400 mt-1">
                {t("chat.tokens", {
                  prompt: turn.response.usage.prompt_tokens,
                  completion: turn.response.usage.completion_tokens,
                })}
              </p>
            </div>
          </div>
        ))}
        {chatMutation.isPending && (
          <div className="flex items-center gap-2 text-sm text-slate-500 italic">
            <span className="animate-pulse">{t("chat.thinking")}</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex gap-2 pt-3 border-t border-slate-200">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("chat.placeholder")}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
          disabled={chatMutation.isPending}
        />
        <Button
          onClick={handleSend}
          disabled={!input.trim() || !selectedLlm || chatMutation.isPending}
          size="sm"
        >
          <Send className="h-4 w-4" />
          {t("chat.send")}
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Vérifier TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Commit**

```bash
git add frontend/src/pages/workspace/PlaygroundLlmConfigTab.tsx \
        frontend/src/pages/workspace/PlaygroundChatTab.tsx
git commit -m "feat(front): PlaygroundLlmConfigTab + PlaygroundChatTab"
```

---

## Task 9 : WorkspacePlaygroundTab + WorkspaceDetailPanel

**Files:**
- Create: `frontend/src/pages/workspace/WorkspacePlaygroundTab.tsx`
- Modify: `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx`

- [ ] **Créer `frontend/src/pages/workspace/WorkspacePlaygroundTab.tsx`**

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PlaygroundLlmConfigTab } from "./PlaygroundLlmConfigTab";
import { PlaygroundChatTab } from "./PlaygroundChatTab";

interface Props {
  workspaceName: string;
}

export function WorkspacePlaygroundTab({ workspaceName }: Props) {
  const { t } = useTranslation("playground");
  const [sub, setSub] = useState("chat");

  return (
    <Tabs value={sub} onValueChange={setSub}>
      <TabsList>
        <TabsTrigger value="chat">{t("tabs.chat")}</TabsTrigger>
        <TabsTrigger value="config">{t("tabs.config")}</TabsTrigger>
      </TabsList>
      <TabsContent value="chat" className="pt-4">
        <PlaygroundChatTab workspaceName={workspaceName} />
      </TabsContent>
      <TabsContent value="config" className="pt-4">
        <PlaygroundLlmConfigTab workspaceName={workspaceName} />
      </TabsContent>
    </Tabs>
  );
}
```

- [ ] **Modifier `WorkspaceDetailPanel.tsx`**

Ajouter l'import :
```tsx
import { WorkspacePlaygroundTab } from "./WorkspacePlaygroundTab";
```

Après `<TabsTrigger value="webhooks">`, ajouter :
```tsx
<TabsTrigger value="playground">{t("tabs.playground")}</TabsTrigger>
```

Après le `<TabsContent value="webhooks">`, ajouter :
```tsx
<TabsContent value="playground" className="pt-4">
  <WorkspacePlaygroundTab workspaceName={ws.name} />
</TabsContent>
```

- [ ] **Vérifier TypeScript + lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

- [ ] **Commit**

```bash
git add frontend/src/pages/workspace/WorkspacePlaygroundTab.tsx \
        frontend/src/pages/workspace/WorkspaceDetailPanel.tsx
git commit -m "feat(front): onglet Playground dans WorkspaceDetailPanel"
```
