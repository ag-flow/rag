"""Parité d'attribution entre les deux surfaces porteuses de clé API.

Le défaut corrigé n'était visible d'aucun test unitaire pris isolément : MCP et
REST étaient chacun cohérents, mais divergeaient entre eux. On vérifie donc la
propriété qui compte — pour une MÊME clé et une MÊME identité signée, les deux
chemins attribuent le MÊME `owner_id`.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.api.mcp_standard import RagMcpDispatcher, _ws_ctx
from rag.auth.obo import sign_actor
from rag.auth.owner import principal_to_owner_id
from rag.auth.workspace_auth import require_apikey_owner

_API_KEY = "shared-key-EXAMPLE"
_ACTOR = "3f2a9c81-0000-4000-8000-000000000001"
_KEY_OWNER = "k" * 64
_HUMAN_EMAIL = "gael@yoops.org"


def _raw_headers(*, with_obo: bool) -> list[tuple[bytes, bytes]]:
    headers = [(b"authorization", f"Bearer {_API_KEY}".encode())]
    if not with_obo:
        return headers
    ts = int(time.time())
    return [
        *headers,
        (b"x-portal-actor", _ACTOR.encode()),
        (b"x-portal-actor-timestamp", str(ts).encode()),
        (b"x-portal-actor-signature", sign_actor(_ACTOR, ts, _API_KEY).encode()),
    ]


def _pool(identity_email: str | None) -> MagicMock:
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={"owner_id": _KEY_OWNER, "scope": "admin"})
    pool.fetchval = AsyncMock(return_value=identity_email)
    return pool


class _Headers:
    def __init__(self, raw: list[tuple[bytes, bytes]]) -> None:
        self.raw = raw
        self._map = {name.decode().lower(): value.decode() for name, value in raw}

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._map.get(key.lower(), default)


async def _rest_owner(raw: list[tuple[bytes, bytes]], pool: MagicMock) -> str:
    request = SimpleNamespace(
        headers=_Headers(raw),
        app=SimpleNamespace(state=SimpleNamespace(pools=SimpleNamespace(config_pool=pool))),
    )
    ctx = await require_apikey_owner(request)  # type: ignore[arg-type]
    return ctx.owner_id


async def _mcp_ctx(raw: list[tuple[bytes, bytes]], pool: MagicMock):
    """Traverse le dispatcher MCP et capture le contexte posé dans `_ws_ctx`."""
    captured = {}

    async def _inner(scope, receive, send) -> None:
        captured["ctx"] = _ws_ctx.get()

    dispatcher = RagMcpDispatcher(_inner)
    dispatcher.set_app_state(
        SimpleNamespace(
            pools=SimpleNamespace(config_pool=pool),
            resolver=None,
            client_provider=None,
        )
    )
    scope = {"type": "http", "path": "/", "headers": raw}
    await dispatcher(scope, AsyncMock(), AsyncMock())
    return captured["ctx"]


@pytest.mark.asyncio
async def test_both_surfaces_attribute_the_same_human_owner() -> None:
    """Régression : le workspace créé via MCP doit rester joignable en REST."""
    human_owner = principal_to_owner_id(_HUMAN_EMAIL)
    raw = _raw_headers(with_obo=True)

    rest_owner = await _rest_owner(raw, _pool(_HUMAN_EMAIL))
    mcp_ctx = await _mcp_ctx(raw, _pool(_HUMAN_EMAIL))

    assert rest_owner == mcp_ctx.owner_id == human_owner
    assert mcp_ctx.owner_source == "obo"


@pytest.mark.asyncio
async def test_both_surfaces_fall_back_to_the_same_key_owner() -> None:
    """Sans identité propagée, les deux surfaces retombent identiquement."""
    raw = _raw_headers(with_obo=False)

    rest_owner = await _rest_owner(raw, _pool(_HUMAN_EMAIL))
    mcp_ctx = await _mcp_ctx(raw, _pool(_HUMAN_EMAIL))

    assert rest_owner == mcp_ctx.owner_id == _KEY_OWNER
    assert mcp_ctx.owner_source == "apikey"


@pytest.mark.asyncio
async def test_both_surfaces_ignore_an_unknown_identity_identically() -> None:
    raw = _raw_headers(with_obo=True)

    rest_owner = await _rest_owner(raw, _pool(None))
    mcp_ctx = await _mcp_ctx(raw, _pool(None))

    assert rest_owner == mcp_ctx.owner_id == _KEY_OWNER
    assert mcp_ctx.owner_source == "apikey"
