from __future__ import annotations

from hashlib import sha256
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.schemas.workspace import (
    PushIndexedResponse,
    PushRequest,
    PushSkippedResponse,
)
from rag.services.push import push_document


class _FakeIndexer:
    def __init__(self, returns_chunks: int = 3) -> None:
        self.returns_chunks = returns_chunks
        self.calls: list[dict[str, Any]] = []

    async def index_file(self, **kw: Any) -> int:
        self.calls.append(kw)
        return self.returns_chunks

    async def delete_file(self, **kw: Any) -> None:
        raise AssertionError("not expected")


def _hash(content: str) -> str:
    return "sha256:" + sha256(content.encode("utf-8")).hexdigest()


@pytest.mark.asyncio
async def test_push_indexes_when_hash_differs() -> None:
    indexer = _FakeIndexer(returns_chunks=4)
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=None)  # rien indexé encore

    ws = uuid4()
    payload = PushRequest(path="docs/foo.md", content="hello world")
    resp = await push_document(
        payload=payload,
        workspace_id=ws,
        indexer_used="openai/text-embedding-3-small",
        config_pool=pool,
        indexer=indexer,
    )

    assert isinstance(resp, PushIndexedResponse)
    assert resp.path == "docs/foo.md"
    assert resp.chunks == 4
    assert resp.hash == _hash("hello world")
    assert len(indexer.calls) == 1
    assert indexer.calls[0]["workspace_id"] == ws
    assert indexer.calls[0]["path"] == "docs/foo.md"
    assert indexer.calls[0]["content_hash"] == _hash("hello world")
    assert indexer.calls[0]["indexer_used"] == "openai/text-embedding-3-small"


@pytest.mark.asyncio
async def test_push_skips_when_hash_identical() -> None:
    content = "stable content"
    indexer = _FakeIndexer()
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=_hash(content))

    payload = PushRequest(path="x.md", content=content)
    resp = await push_document(
        payload=payload,
        workspace_id=uuid4(),
        indexer_used="openai/m",
        config_pool=pool,
        indexer=indexer,
    )

    assert isinstance(resp, PushSkippedResponse)
    assert resp.path == "x.md"
    assert resp.reason == "content_unchanged"
    assert indexer.calls == []  # pas d'appel embed


@pytest.mark.asyncio
async def test_push_normalizes_path_before_indexing() -> None:
    indexer = _FakeIndexer(returns_chunks=1)
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=None)

    payload = PushRequest(path="docs\\sub\\foo.md", content="x")
    resp = await push_document(
        payload=payload,
        workspace_id=uuid4(),
        indexer_used="openai/m",
        config_pool=pool,
        indexer=indexer,
    )

    assert resp.path == "docs/sub/foo.md"
    assert indexer.calls[0]["path"] == "docs/sub/foo.md"


@pytest.mark.asyncio
async def test_push_raises_invalid_path_for_traversal() -> None:
    from rag.api.errors import InvalidPath

    indexer = _FakeIndexer()
    pool = MagicMock()
    pool.fetchval = AsyncMock()

    payload = PushRequest(path="foo/../bar", content="x")
    with pytest.raises(InvalidPath):
        await push_document(
            payload=payload,
            workspace_id=uuid4(),
            indexer_used="openai/m",
            config_pool=pool,
            indexer=indexer,
        )
    pool.fetchval.assert_not_called()


@pytest.mark.asyncio
async def test_push_zero_chunks_still_returns_indexed_response() -> None:
    indexer = _FakeIndexer(returns_chunks=0)
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=None)

    payload = PushRequest(path="empty.md", content=" ")
    resp = await push_document(
        payload=payload,
        workspace_id=uuid4(),
        indexer_used="openai/m",
        config_pool=pool,
        indexer=indexer,
    )
    assert isinstance(resp, PushIndexedResponse)
    assert resp.chunks == 0
