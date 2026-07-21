"""Handshake MCP protocolaire de bout en bout sur `/mcp` (connecteur unique).

Garde-fou contre trois régressions qui rendaient l'endpoint « down » :
1. l'endpoint réel était `/mcp/mcp` (streamable_http_path par défaut) ;
2. la protection DNS-rebinding rejetait le Host public ;
3. le session manager n'était pas démarré (lifespan de sous-app non exécuté).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Mount

from rag.api.mcp_standard import (
    McpPathNormalizerMiddleware,
    RagMcpDispatcher,
    build_mcp_asgi,
    mcp_session_lifespan,
)

_INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "t", "version": "1"},
    },
}
_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def _parse(text: str) -> dict:
    for line in text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    return json.loads(text)


def _dispatcher(scope: str = "read") -> RagMcpDispatcher:
    disp = RagMcpDispatcher(build_mcp_asgi())
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={"owner_id": "o", "scope": scope})
    state = MagicMock()
    state.pools = MagicMock()
    state.pools.config_pool = pool
    state.resolver = MagicMock()
    state.client_provider = MagicMock()
    state.client_provider.get_default_vault_name = AsyncMock(return_value=None)
    disp.set_app_state(state)
    return disp


@pytest.mark.asyncio
async def test_initialize_handshake_succeeds_on_mcp_without_slash() -> None:
    # Normaliseur en amont : `/mcp` (SANS slash) doit aboutir DIRECTEMENT, sans
    # 307 — les clients MCP streamable ne suivent pas la redirection.
    parent = Starlette(routes=[Mount("/mcp", app=_dispatcher())])
    app = McpPathNormalizerMiddleware(parent)
    transport = httpx.ASGITransport(app=app)
    # Host public (hors localhost) : valide la levée de la protection DNS-rebinding.
    # PAS de follow_redirects : on exige que `/mcp` marche tel quel.
    async with (
        mcp_session_lifespan(),
        httpx.AsyncClient(transport=transport, base_url="https://rag.yoops.org") as client,
    ):
        resp = await client.post(
            "/mcp", json=_INIT, headers={**_HEADERS, "Authorization": "Bearer k"}
        )
        assert resp.status_code == 200
        data = _parse(resp.text)
        assert data["result"]["protocolVersion"]
        assert "serverInfo" in data["result"]


@pytest.mark.asyncio
async def test_handshake_without_bearer_is_401() -> None:
    parent = Starlette(routes=[Mount("/mcp", app=_dispatcher())])
    transport = httpx.ASGITransport(app=parent)
    async with (
        mcp_session_lifespan(),
        httpx.AsyncClient(
            transport=transport, base_url="https://rag.yoops.org", follow_redirects=True
        ) as client,
    ):
        resp = await client.post("/mcp", json=_INIT, headers=_HEADERS)
        assert resp.status_code == 401
