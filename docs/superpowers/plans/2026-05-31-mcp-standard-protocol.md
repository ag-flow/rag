# Serveur MCP Standard (Streamable HTTP) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un serveur MCP natif (Streamable HTTP) au service RAG, exposant un outil `rag_search` consommable directement par Claude Code sans wrapper local.

**Architecture:** Un dispatcher ASGI unique monté sur `/mcp` extrait le `workspace_id` du path, valide le Bearer token contre `workspace_api_keys`, injecte le contexte workspace dans un `ContextVar`, puis délègue à une app `FastMCP` partagée avec `stateless_http=True`. L'outil `rag_search` lit le contextvar pour effectuer la recherche vectorielle. L'onglet "API Keys" est renommé "Api" et affiche la config de connexion MCP prête à copier.

**Tech Stack:** Python 3.12, `mcp>=1.27.2` (FastMCP, StreamableHTTP), FastAPI, asyncpg, React 18, TanStack Query, i18next.

---

## Contexte pour l'agent

- **Branche :** `dev` — vérifier `git branch --show-current` avant tout edit.
- **SDK MCP déjà installé** : `mcp>=1.27.2` dans `pyproject.toml`.
- **Patterns backend** : asyncpg direct, structlog, pas SQLAlchemy, `app.state` accessible dans les handlers.
- **`workspace_api_keys`** : table multi-clés (migration 033). `fingerprint = SHA-256(token)`. Grace period 72h.
- **`ApiKeyCache`** : dans `rag.auth.workspace_auth`. `.get(ref)` / `.put(ref, value)`.
- **`app.state` en lifespan** : `pools.config_pool`, `resolver`, `client_provider`, `apikey_cache`.
- **Frontend** : `Workspace.id` est l'UUID (déjà dans `workspaces.types.ts`). `VITE_PUBLIC_URL` → fallback `window.location.origin`.
- **Pas de `__import__()` en production** — utiliser les imports en tête de fichier ou imports locaux dans la fonction.

---

## Task 1 — Backend : `mcp_standard.py` (dispatcher + tool)

**Files:**
- Create: `backend/src/rag/api/mcp_standard.py`
- Create: `backend/tests/unit/test_mcp_dispatcher.py`

- [ ] **Step 1 : Écrire les tests (rouge)**

```python
# backend/tests/unit/test_mcp_dispatcher.py
from __future__ import annotations

import hashlib
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.api.mcp_standard import RagMcpDispatcher, _extract_workspace_id, _extract_bearer


def test_extract_workspace_id_valid() -> None:
    assert _extract_workspace_id("/550e8400-e29b-41d4-a716-446655440000") == "550e8400-e29b-41d4-a716-446655440000"


def test_extract_workspace_id_with_trailing() -> None:
    assert _extract_workspace_id("/550e8400-e29b-41d4-a716-446655440000/mcp") == "550e8400-e29b-41d4-a716-446655440000"


def test_extract_workspace_id_empty_returns_none() -> None:
    assert _extract_workspace_id("/") is None


def test_extract_workspace_id_invalid_uuid_returns_none() -> None:
    assert _extract_workspace_id("/not-a-uuid") is None


def test_extract_bearer_valid() -> None:
    headers = [(b"authorization", b"Bearer my-token")]
    assert _extract_bearer(headers) == "my-token"


def test_extract_bearer_missing_returns_none() -> None:
    assert _extract_bearer([]) is None


def test_extract_bearer_non_bearer_returns_none() -> None:
    headers = [(b"authorization", b"Basic abc")]
    assert _extract_bearer(headers) is None


@pytest.mark.asyncio
async def test_dispatcher_404_no_workspace_id() -> None:
    inner = AsyncMock()
    dispatcher = RagMcpDispatcher(inner)
    responses = []

    async def send(msg):
        responses.append(msg)

    scope = {"type": "http", "path": "/", "headers": [], "method": "POST"}
    await dispatcher(scope, AsyncMock(), send)

    assert responses[0]["status"] == 404


@pytest.mark.asyncio
async def test_dispatcher_401_no_token() -> None:
    inner = AsyncMock()
    dispatcher = RagMcpDispatcher(inner)
    responses = []

    async def send(msg):
        responses.append(msg)

    scope = {
        "type": "http",
        "path": "/550e8400-e29b-41d4-a716-446655440000",
        "headers": [],
        "method": "POST",
    }
    await dispatcher(scope, AsyncMock(), send)

    assert responses[0]["status"] == 401


@pytest.mark.asyncio
async def test_dispatcher_503_when_state_not_ready() -> None:
    inner = AsyncMock()
    dispatcher = RagMcpDispatcher(inner)
    responses = []

    async def send(msg):
        responses.append(msg)

    scope = {
        "type": "http",
        "path": "/550e8400-e29b-41d4-a716-446655440000",
        "headers": [(b"authorization", b"Bearer mytoken")],
        "method": "POST",
    }
    await dispatcher(scope, AsyncMock(), send)

    assert responses[0]["status"] == 503
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_mcp_dispatcher.py -v 2>&1 | head -10
```

Expected : `ImportError`

- [ ] **Step 3 : Implémenter `mcp_standard.py`**

```python
# backend/src/rag/api/mcp_standard.py
from __future__ import annotations

import json
from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256
from secrets import compare_digest
from typing import Any
from uuid import UUID

import asyncpg
import structlog
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.types import ASGIApp, Receive, Scope, Send

log = structlog.get_logger(__name__)

# ── Context workspace propagé par requête ────────────────────────────────────

@dataclass(frozen=True)
class _WsCtx:
    workspace_name: str
    rag_cnx: str
    indexer_provider: str
    indexer_model: str
    indexer_api_key_ref: str | None
    indexer_base_url: str | None
    pool_registry: Any
    resolver: Any


_ws_ctx: ContextVar[_WsCtx] = ContextVar("mcp_ws_ctx")

# ── FastMCP server (singleton, stateless) ────────────────────────────────────

_mcp = FastMCP("rag", stateless_http=True)


@_mcp.tool()
async def rag_search(query: str, top_k: int = 5, min_score: float = 0.3) -> str:
    """Recherche sémantique dans le corpus RAG du workspace courant.

    Retourne les chunks pertinents au format markdown, triés par score décroissant.
    """
    from rag.db.workspace_search import vector_search
    from rag.indexer.providers.factory import make_provider
    from rag.secrets.refs import is_vault_ref

    ctx = _ws_ctx.get()

    api_key: str | None = None
    if ctx.indexer_api_key_ref and is_vault_ref(ctx.indexer_api_key_ref):
        api_key = await ctx.resolver.resolve_with_retry(ctx.indexer_api_key_ref)

    provider = make_provider(
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
    )

    if not hits:
        return "Aucun résultat pertinent trouvé dans le corpus."

    parts = [
        f"[{h.path} — chunk {h.chunk_index} — score {h.score:.3f}]\n{h.content}"
        for h in hits
    ]
    log.info("mcp_standard.search", workspace=ctx.workspace_name, hits=len(hits))
    return "\n\n---\n\n".join(parts)


def build_mcp_asgi() -> Starlette:
    """Retourne l'app Starlette FastMCP (stateless). Appelé une seule fois."""
    return _mcp.streamable_http_app()


# ── Helpers (exportés pour les tests) ────────────────────────────────────────

def _extract_workspace_id(path: str) -> str | None:
    """Extrait et valide le premier segment du path comme UUID workspace."""
    segments = [s for s in path.split("/") if s]
    if not segments:
        return None
    candidate = segments[0]
    try:
        UUID(candidate)
    except ValueError:
        return None
    return candidate


def _extract_bearer(headers: list[tuple[bytes, bytes]]) -> str | None:
    """Extrait le token Bearer du header Authorization."""
    for name, value in headers:
        if name.lower() == b"authorization":
            decoded = value.decode()
            if decoded.startswith("Bearer "):
                return decoded[7:]
    return None


# ── ASGI Dispatcher ──────────────────────────────────────────────────────────

class RagMcpDispatcher:
    """Dispatcher ASGI monté sur /mcp dans FastAPI.

    - Extrait workspace_id du path (/{workspace_id}/...)
    - Valide le Bearer token via workspace_api_keys
    - Injecte le contexte workspace dans _ws_ctx
    - Réécrit le path (supprime le segment workspace_id)
    - Délègue à l'inner FastMCP app
    """

    def __init__(self, inner: ASGIApp) -> None:
        self._inner = inner
        # Injecté depuis le lifespan via set_app_state()
        self._config_pool: asyncpg.Pool | None = None
        self._pool_registry: Any = None
        self._resolver: Any = None
        self._apikey_cache: Any = None

    def set_app_state(self, app_state: Any) -> None:
        """Appelé depuis le lifespan après initialisation des pools."""
        self._config_pool = app_state.pools.config_pool
        self._pool_registry = app_state.pools
        self._resolver = app_state.resolver
        self._apikey_cache = app_state.apikey_cache

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._inner(scope, receive, send)
            return

        if self._config_pool is None:
            await _json_error(send, 503, "service_not_ready")
            return

        path: str = scope.get("path", "/")
        workspace_id = _extract_workspace_id(path)
        if workspace_id is None:
            await _json_error(send, 404, "workspace_id_required")
            return

        token = _extract_bearer(scope.get("headers", []))
        if token is None:
            await _json_error(send, 401, "authorization_required")
            return

        try:
            ctx = await self._load_context(workspace_id, token)
        except PermissionError:
            await _json_error(send, 401, "invalid_token")
            return
        except LookupError:
            await _json_error(send, 404, "workspace_not_found")
            return

        # Réécriture du path : supprimer le segment workspace_id
        segments = [s for s in path.split("/") if s]
        remaining = "/" + "/".join(segments[1:]) if len(segments) > 1 else "/"
        new_scope = {**scope, "path": remaining, "raw_path": remaining.encode()}

        token_var = _ws_ctx.set(ctx)
        try:
            await self._inner(new_scope, receive, send)
        finally:
            _ws_ctx.reset(token_var)

    async def _load_context(self, workspace_id: str, token: str) -> _WsCtx:
        assert self._config_pool is not None  # noqa: S101
        fingerprint = sha256(token.encode()).hexdigest()

        row = await self._config_pool.fetchrow(
            """
            SELECT w.name, w.rag_cnx,
                   k.api_key_ref,
                   ic.provider, ic.model,
                   ic.api_key_ref AS indexer_api_key_ref,
                   ic.base_url
            FROM workspaces w
            JOIN workspace_api_keys k ON k.workspace_id = w.id
            JOIN indexer_configs ic ON ic.workspace_id = w.id
            WHERE w.id = $1::uuid
              AND k.fingerprint = $2
              AND k.revoked_at IS NULL
              AND (k.rotated_at IS NULL OR k.rotated_at > now() - interval '72 hours')
            """,
            workspace_id,
            fingerprint,
        )

        if row is None:
            exists = await self._config_pool.fetchval(
                "SELECT 1 FROM workspaces WHERE id = $1::uuid", workspace_id
            )
            if not exists:
                raise LookupError(workspace_id)
            raise PermissionError("invalid token")

        api_key_ref: str = row["api_key_ref"]
        cached = self._apikey_cache.get(api_key_ref)
        if cached is None:
            cached = await self._resolver.resolve_with_retry(api_key_ref)
            self._apikey_cache.put(api_key_ref, cached)

        if not compare_digest(cached, token):
            raise PermissionError("token mismatch")

        return _WsCtx(
            workspace_name=str(row["name"]),
            rag_cnx=str(row["rag_cnx"]),
            indexer_provider=str(row["provider"]),
            indexer_model=str(row["model"]),
            indexer_api_key_ref=row["indexer_api_key_ref"],
            indexer_base_url=row["base_url"],
            pool_registry=self._pool_registry,
            resolver=self._resolver,
        )


async def _json_error(send: Send, status: int, detail: str) -> None:
    body = json.dumps({"error": detail}).encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [[b"content-type", b"application/json"]],
    })
    await send({"type": "http.response.body", "body": body, "more_body": False})
```

- [ ] **Step 4 : Vérifier les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_mcp_dispatcher.py -v
```

Expected : `9 passed`

- [ ] **Step 5 : Lint**

```bash
cd backend && uv run ruff check src/rag/api/mcp_standard.py
```

Expected : 0 erreurs

- [ ] **Step 6 : Commit**

```bash
git add backend/src/rag/api/mcp_standard.py \
        backend/tests/unit/test_mcp_dispatcher.py \
        backend/pyproject.toml backend/uv.lock
git commit -m "feat(mcp): serveur MCP standard Streamable HTTP — dispatcher + rag_search tool"
```

---

## Task 2 — Backend : intégration dans `main.py`

**Files:**
- Modify: `backend/src/rag/main.py`

- [ ] **Step 1 : Lire `main.py` pour trouver les bons emplacements**

Lire `backend/src/rag/main.py` pour localiser :
1. La section des imports en tête
2. L'endroit où les routers sont enregistrés (`app.include_router(...)`)
3. Le lifespan context manager (où `app.state` est peuplé)

- [ ] **Step 2 : Ajouter l'import**

Dans la section des imports de `main.py`, ajouter :
```python
from rag.api.mcp_standard import RagMcpDispatcher, build_mcp_asgi
```

- [ ] **Step 3 : Créer le dispatcher avant l'app**

Dans la fonction `build_app()`, avant la création de `FastAPI(...)`, ajouter :
```python
_mcp_dispatcher = RagMcpDispatcher(build_mcp_asgi())
```

- [ ] **Step 4 : Monter le dispatcher**

Dans la section `include_router`, après `app.include_router(build_mcp_router())`, ajouter :
```python
app.mount("/mcp", _mcp_dispatcher)
```

- [ ] **Step 5 : Injecter l'état dans le lifespan**

Dans le lifespan (après l'initialisation des pools et avant le `yield`), ajouter :
```python
_mcp_dispatcher.set_app_state(app.state)
```

- [ ] **Step 6 : Vérifier que l'app démarre**

```bash
cd backend && uv run python -c "
from rag.main import build_app
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://x:x@localhost/x')
os.environ.setdefault('RAG_POSTGRES_ADMIN_URL', 'postgresql://x:x@localhost/x')
os.environ.setdefault('RAG_MASTER_KEY', 'x' * 32)
os.environ.setdefault('RAG_PUBLIC_URL', 'http://localhost:8000')
os.environ.setdefault('HARPOCRATE_DEK', 'x' * 32)
app = build_app()
print('routes with /mcp:', [r.path for r in app.routes if hasattr(r, 'path') and 'mcp' in str(getattr(r, 'path', ''))])
print('mounts:', [r.path for r in app.routes if hasattr(r, 'path') and hasattr(r, 'app')])
"
```

Expected : `/mcp` visible dans les mounts.

- [ ] **Step 7 : Vérifier le lint**

```bash
cd backend && uv run ruff check src/rag/main.py
```

Expected : 0 erreurs

- [ ] **Step 8 : Commit**

```bash
git add backend/src/rag/main.py
git commit -m "feat(mcp): monter RagMcpDispatcher sur /mcp dans FastAPI"
```

---

## Task 3 — Frontend : section Connexion MCP + renommage onglet

**Files:**
- Modify: `frontend/src/pages/workspace/WorkspaceApiKeysTab.tsx`
- Modify: `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx`
- Modify: `frontend/src/i18n/fr/apikeys.json`
- Modify: `frontend/src/i18n/en/apikeys.json`

- [ ] **Step 1 : Ajouter les clés i18n**

Dans `frontend/src/i18n/fr/apikeys.json`, ajouter après les clés existantes :
```json
  "mcp_section_title": "Connexion MCP",
  "mcp_url_label": "URL du serveur MCP",
  "mcp_token_hint": "Token d'accès → utiliser une clé API ci-dessous",
  "mcp_config_label": "Config Claude Code (.claude/mcp.json)",
  "mcp_copied": "Copié !"
```

Dans `frontend/src/i18n/en/apikeys.json` :
```json
  "mcp_section_title": "MCP Connection",
  "mcp_url_label": "MCP server URL",
  "mcp_token_hint": "Access token → use an API key below",
  "mcp_config_label": "Claude Code config (.claude/mcp.json)",
  "mcp_copied": "Copied!"
```

- [ ] **Step 2 : Mettre à jour `WorkspaceApiKeysTab.tsx`**

Lire le fichier existant pour comprendre la structure, puis :

**2a.** Ajouter la prop `workspaceId: string` à l'interface Props :
```tsx
interface Props {
  workspaceName: string;
  workspaceId: string;
}
```

**2b.** Mettre à jour la signature de la fonction :
```tsx
export function WorkspaceApiKeysTab({ workspaceName, workspaceId }: Props) {
```

**2c.** Ajouter les imports nécessaires en tête :
```tsx
import { useState } from "react";  // si pas déjà présent
import { Copy, Check } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
```

**2d.** Ajouter l'état copie et la logique avant le `return` :
```tsx
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [copiedConfig, setCopiedConfig] = useState(false);

  const publicUrl = import.meta.env.VITE_PUBLIC_URL ?? window.location.origin;
  const mcpUrl = `${publicUrl}/mcp/${workspaceId}`;
  const mcpConfig = JSON.stringify(
    {
      [workspaceName]: {
        url: mcpUrl,
        headers: { Authorization: "Bearer <votre-clé>" },
      },
    },
    null,
    2,
  );

  async function copyText(text: string, setCopied: (v: boolean) => void) {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }
```

**2e.** Ajouter la section Connexion MCP **avant** le bouton "Ajouter" existant, dans le JSX :
```tsx
      {/* Section Connexion MCP */}
      <section className="rounded-md border border-slate-200 bg-slate-50 p-4 space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          {t("mcp_section_title")}
        </h3>
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">{t("mcp_url_label")}</Label>
          <div className="flex items-center gap-2">
            <Input value={mcpUrl} readOnly className="font-mono text-xs bg-white" />
            <Button
              size="sm"
              variant="outline"
              onClick={() => copyText(mcpUrl, setCopiedUrl)}
              className="shrink-0"
            >
              {copiedUrl ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            </Button>
          </div>
        </div>
        <p className="text-xs text-slate-500">{t("mcp_token_hint")}</p>
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">{t("mcp_config_label")}</Label>
          <div className="flex items-start gap-2">
            <textarea
              value={mcpConfig}
              readOnly
              rows={7}
              className="w-full rounded-md border border-slate-200 bg-white p-2 font-mono text-xs resize-none"
            />
            <Button
              size="sm"
              variant="outline"
              onClick={() => copyText(mcpConfig, setCopiedConfig)}
              className="shrink-0 mt-0.5"
            >
              {copiedConfig ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            </Button>
          </div>
        </div>
      </section>
```

- [ ] **Step 3 : Mettre à jour `WorkspaceDetailPanel.tsx`**

**3a.** Trouver la ligne avec `<TabsTrigger value="apikeys">` et changer le label :
```tsx
<TabsTrigger value="apikeys">{t("tabs.api")}</TabsTrigger>
```

**3b.** Trouver la `TabsContent value="apikeys"` et passer la nouvelle prop :
```tsx
<TabsContent value="apikeys" className="pt-4">
  <WorkspaceApiKeysTab workspaceName={ws.name} workspaceId={ws.id} />
</TabsContent>
```

- [ ] **Step 4 : Ajouter la clé i18n du tab dans `fr/workspace.json` et `en/workspace.json`**

Dans `frontend/src/i18n/fr/workspace.json`, dans la section `tabs`, remplacer ou ajouter :
```json
"api": "Api"
```

Dans `frontend/src/i18n/en/workspace.json` :
```json
"api": "Api"
```

- [ ] **Step 5 : Vérifier TypeScript + lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Expected : 0 erreurs TypeScript

- [ ] **Step 6 : Commit**

```bash
git add frontend/src/pages/workspace/WorkspaceApiKeysTab.tsx \
        frontend/src/pages/workspace/WorkspaceDetailPanel.tsx \
        frontend/src/i18n/fr/apikeys.json \
        frontend/src/i18n/en/apikeys.json \
        frontend/src/i18n/fr/workspace.json \
        frontend/src/i18n/en/workspace.json
git commit -m "feat(front): onglet Api — section Connexion MCP + URL/config Claude Code"
```

---

## Self-review

**Couverture spec :**
- ✅ Transport Streamable HTTP via FastMCP `stateless_http=True` (Task 1)
- ✅ Endpoint `/mcp/{workspace_id}` (Task 1 + 2)
- ✅ Outil `rag_search(query, top_k, min_score)` (Task 1)
- ✅ Workspace implicite dans l'URL (Task 1 — pas dans les params outil)
- ✅ Auth Bearer token via `workspace_api_keys` + `ApiKeyCache` (Task 1)
- ✅ 401 token invalide, 404 workspace inconnu, 503 non prêt (Task 1 tests)
- ✅ Initialize name `"rag"` — simple, workspace identifié par l'URL (Task 1)
- ✅ Résultat Markdown : `[path — chunk N — score X]\ncontenu` (Task 1)
- ✅ `RAG_PUBLIC_URL` / `VITE_PUBLIC_URL` → fallback `window.location.origin` (Task 3)
- ✅ Onglet "Api" renommé (Task 3)
- ✅ Section Connexion MCP avec URL + config JSON prête à copier (Task 3)

**Consistance types :**
- `RagMcpDispatcher` exporté → utilisé dans `main.py` (Task 2) ✅
- `build_mcp_asgi()` exporté → utilisé dans `main.py` (Task 2) ✅
- `_extract_workspace_id`, `_extract_bearer` exportés → testés dans Task 1 ✅
- `workspaceId: string` ajouté à Props et passé depuis `WorkspaceDetailPanel` ✅
- `ws.id` est bien `string` dans `Workspace` type (déjà vérifié) ✅
