from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from rag.indexer.chunking.markdown_deep import MarkdownDeepChunker
from rag.indexer.chunking.routing_chunker import RoutingChunker
from rag.indexer.chunking.tokens import HeuristicTokenEstimator
from rag.services.chunking_routing import (
    StrategyBindingLostError,
    StrategyRecord,
    build_strategy_chunker,
)

_EST = HeuristicTokenEstimator(char_ratio=4.0)


class _FakeConn:
    """Connexion minimale : sert les routes et les stratégies par id."""

    def __init__(self, routes: list[dict[str, Any]], strategies: dict[Any, dict[str, Any]]):
        self._routes = routes
        self._strategies = strategies
        self.queries: list[str] = []

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        self.queries.append(query)
        assert "chunking_strategy_region_routes" in query
        return self._routes

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        self.queries.append(query)
        assert "chunking_strategies" in query
        return self._strategies.get(args[0])


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


def _record(**overrides: Any) -> StrategyRecord:
    defaults: dict[str, Any] = {
        "id": uuid4(),
        "slug": "ma-strategie",
        "algo": "prose",
        "params": {},
        "parser_slug": None,
    }
    return StrategyRecord(**{**defaults, **overrides})


@pytest.mark.asyncio
async def test_without_parser_no_db_access_and_plain_chunker() -> None:
    """Sans parser_slug : chemin existant inchangé, aucune requête de routes."""
    conn = _FakeConn(routes=[], strategies={})
    chunker = await build_strategy_chunker(
        _FakePool(conn),  # type: ignore[arg-type]
        _record(),
        estimator=_EST,
        provider_max_input_tokens=8192,
    )
    assert isinstance(chunker, MarkdownDeepChunker)
    assert conn.queries == []


@pytest.mark.asyncio
async def test_with_parser_builds_routing_chunker() -> None:
    record = _record(parser_slug="markdown")
    conn = _FakeConn(
        routes=[
            {
                "region_type": "table",
                "qualifier": "*",
                "target_strategy_id": None,
                "atomic": True,
                "overflow_policy": "keep_whole",
            }
        ],
        strategies={},
    )
    chunker = await build_strategy_chunker(
        _FakePool(conn),  # type: ignore[arg-type]
        record,
        estimator=_EST,
        provider_max_input_tokens=8192,
    )
    assert isinstance(chunker, RoutingChunker)


@pytest.mark.asyncio
async def test_route_targets_loaded_by_id() -> None:
    target_id = uuid4()
    record = _record(parser_slug="markdown")
    conn = _FakeConn(
        routes=[
            {
                "region_type": "code_fence",
                "qualifier": "mermaid",
                "target_strategy_id": target_id,
                "atomic": False,
                "overflow_policy": "parent_only",
            }
        ],
        strategies={
            target_id: {
                "id": target_id,
                "slug": "cible",
                "algo": "prose",
                "params": {"child_target_tokens": 128},
                "parser_slug": None,
            }
        },
    )
    chunker = await build_strategy_chunker(
        _FakePool(conn),  # type: ignore[arg-type]
        record,
        estimator=_EST,
        provider_max_input_tokens=8192,
    )
    assert isinstance(chunker, RoutingChunker)


@pytest.mark.asyncio
async def test_missing_route_target_raises() -> None:
    record = _record(parser_slug="markdown")
    conn = _FakeConn(
        routes=[
            {
                "region_type": "code_fence",
                "qualifier": "*",
                "target_strategy_id": uuid4(),
                "atomic": False,
                "overflow_policy": "keep_whole",
            }
        ],
        strategies={},
    )
    with pytest.raises(StrategyBindingLostError, match="strategy not found"):
        await build_strategy_chunker(
            _FakePool(conn),  # type: ignore[arg-type]
            record,
            estimator=_EST,
            provider_max_input_tokens=8192,
        )
