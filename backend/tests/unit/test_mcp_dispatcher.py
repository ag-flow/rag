from __future__ import annotations

from unittest.mock import AsyncMock

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
