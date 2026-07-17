from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from rag.services.chunking_routing import (
    StrategyBindingLostError,
    UnknownStrategySlugError,
    load_strategy_by_id,
    resolve_caller_strategy,
)


class _FakeConn:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row
        self.args: tuple[Any, ...] = ()

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        self.args = args
        return self._row


class _FakePool:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    def acquire(self) -> _FakePool._Ctx:
        return _FakePool._Ctx(self._conn)

    class _Ctx:
        def __init__(self, conn: _FakeConn) -> None:
            self._conn = conn

        async def __aenter__(self) -> _FakeConn:
            return self._conn

        async def __aexit__(self, *exc: object) -> None:
            return None


@pytest.mark.asyncio
async def test_resolve_caller_strategy_maps_record() -> None:
    sid = uuid4()
    conn = _FakeConn(
        {"id": sid, "algo": "prose", "params": '{"child_target_tokens": 128}', "parser_slug": None}
    )
    record = await resolve_caller_strategy(
        _FakePool(conn),  # type: ignore[arg-type]
        owner_id="deadbeef",
        slug="ma-strategie",
    )
    assert record.id == sid
    assert record.params == {"child_target_tokens": 128}
    assert conn.args == ("ma-strategie", "deadbeef")


@pytest.mark.asyncio
async def test_resolve_caller_strategy_unknown_slug_raises() -> None:
    conn = _FakeConn(None)
    with pytest.raises(UnknownStrategySlugError, match="ni dans la bibliothèque du caller"):
        await resolve_caller_strategy(
            _FakePool(conn),  # type: ignore[arg-type]
            owner_id="deadbeef",
            slug="fantome",
        )


@pytest.mark.asyncio
async def test_load_strategy_by_id_lost_binding_raises_typed_error() -> None:
    conn = _FakeConn(None)
    with pytest.raises(StrategyBindingLostError, match="bound chunking strategy not found"):
        await load_strategy_by_id(_FakePool(conn), uuid4())  # type: ignore[arg-type]
