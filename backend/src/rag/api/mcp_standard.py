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
    indexer_service: str
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

        path: str = scope.get("path", "/")
        workspace_id = _extract_workspace_id(path)
        if workspace_id is None:
            await _json_error(send, 404, "workspace_id_required")
            return

        token = _extract_bearer(list(scope.get("headers", [])))
        if token is None:
            await _json_error(send, 401, "authorization_required")
            return

        if self._config_pool is None:
            await _json_error(send, 503, "service_not_ready")
            return

        try:
            ctx = await self._load_context(workspace_id, token)
        except PermissionError:
            await _json_error(send, 401, "invalid_token")
            return
        except LookupError:
            await _json_error(send, 404, "workspace_not_found")
            return

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
                   ic.base_url,
                   md.service
            FROM workspaces w
            JOIN workspace_api_keys k ON k.workspace_id = w.id
            JOIN indexer_configs ic ON ic.workspace_id = w.id
            JOIN model_dimensions md ON md.provider = ic.provider AND md.model = ic.model
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
            indexer_service=str(row["service"]),
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
