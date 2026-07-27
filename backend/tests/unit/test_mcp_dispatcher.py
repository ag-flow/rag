from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.api.mcp_standard import RagMcpDispatcher, _extract_bearer


def test_extract_bearer_valid() -> None:
    headers = [(b"authorization", b"Bearer my-token")]
    assert _extract_bearer(headers) == "my-token"


def test_extract_bearer_missing_returns_none() -> None:
    assert _extract_bearer([]) is None


def test_extract_bearer_non_bearer_returns_none() -> None:
    headers = [(b"authorization", b"Basic abc")]
    assert _extract_bearer(headers) is None


@pytest.mark.asyncio
async def test_dispatcher_401_no_token() -> None:
    inner = AsyncMock()
    dispatcher = RagMcpDispatcher(inner)
    responses = []

    async def send(msg):
        responses.append(msg)

    scope = {"type": "http", "path": "/mcp", "headers": [], "method": "POST"}
    await dispatcher(scope, AsyncMock(), send)

    assert responses[0]["status"] == 401
    inner.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatcher_503_when_state_not_ready() -> None:
    inner = AsyncMock()
    dispatcher = RagMcpDispatcher(inner)
    responses = []

    async def send(msg):
        responses.append(msg)

    scope = {
        "type": "http",
        "path": "/mcp",
        "headers": [(b"authorization", b"Bearer mytoken")],
        "method": "POST",
    }
    await dispatcher(scope, AsyncMock(), send)

    assert responses[0]["status"] == 503


@pytest.mark.asyncio
async def test_dispatcher_401_invalid_token() -> None:
    inner = AsyncMock()
    dispatcher = RagMcpDispatcher(inner)
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)  # aucune clé → PermissionError
    dispatcher._config_pool = pool
    responses = []

    async def send(msg):
        responses.append(msg)

    scope = {
        "type": "http",
        "path": "/mcp",
        "headers": [(b"authorization", b"Bearer badtoken")],
        "method": "POST",
    }
    await dispatcher(scope, AsyncMock(), send)

    assert responses[0]["status"] == 401
    inner.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatcher_passes_to_inner_after_auth() -> None:
    inner = AsyncMock()
    dispatcher = RagMcpDispatcher(inner)
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={"owner_id": "owner-1", "scope": "read"})
    dispatcher._config_pool = pool
    dispatcher._pool_registry = MagicMock()
    dispatcher._resolver = MagicMock()
    dispatcher._client_provider = None
    responses = []

    async def send(msg):
        responses.append(msg)

    receive = AsyncMock()
    scope = {
        "type": "http",
        "path": "/mcp",
        "headers": [(b"authorization", b"Bearer goodtoken")],
        "method": "POST",
    }
    await dispatcher(scope, receive, send)

    inner.assert_awaited_once_with(scope, receive, send)
    assert responses == []  # aucune erreur émise par le dispatcher


@pytest.mark.asyncio
async def test_load_context_returns_key_ctx() -> None:
    dispatcher = RagMcpDispatcher(AsyncMock())
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={"owner_id": "owner-xyz", "scope": "admin"})
    dispatcher._config_pool = pool
    dispatcher._pool_registry = MagicMock()
    dispatcher._resolver = MagicMock()
    dispatcher._client_provider = None

    ctx = await dispatcher._load_context("tok")

    assert ctx.owner_id == "owner-xyz"
    assert ctx.scope == "admin"
    sql = pool.fetchrow.await_args.args[0]
    assert "owner_id" in sql
    assert "scope" in sql
    assert "user_api_keys" in sql


@pytest.mark.asyncio
async def test_load_context_invalid_token_raises_permission_error() -> None:
    dispatcher = RagMcpDispatcher(AsyncMock())
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    dispatcher._config_pool = pool

    with pytest.raises(PermissionError):
        await dispatcher._load_context("tok")
