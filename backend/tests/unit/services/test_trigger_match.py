from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from rag.services.trigger_match import resolve_trigger

_WS = uuid4()


class _FakeExecutor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.queries: list[str] = []

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        self.queries.append(query)
        return self._rows


def _trigger(pattern: str, *, strategy: bool = True) -> dict[str, Any]:
    return {"id": uuid4(), "pattern": pattern, "strategy_id": uuid4() if strategy else None}


@pytest.mark.asyncio
async def test_no_trigger_matches() -> None:
    executor = _FakeExecutor([_trigger("datasets/*.csv")])
    result = await resolve_trigger(executor, workspace_id=_WS, path="src/main.py")
    assert result is None


@pytest.mark.asyncio
async def test_most_specific_pattern_wins() -> None:
    generic = _trigger("**/*.md")
    specific = _trigger("backlog/**/*.md")
    executor = _FakeExecutor([generic, specific])
    result = await resolve_trigger(executor, workspace_id=_WS, path="backlog/2026/t.md")
    assert result is not None
    assert result["id"] == specific["id"]


@pytest.mark.asyncio
async def test_tie_goes_to_oldest_created() -> None:
    # L'exécuteur renvoie les lignes triées created_at ASC : à spécificité
    # égale, la première (la plus ancienne) gagne.
    older = _trigger("**/*.md")
    newer = _trigger("**/*.m?")
    executor = _FakeExecutor([older, newer])
    result = await resolve_trigger(executor, workspace_id=_WS, path="guide.md")
    assert result is not None
    assert result["id"] == older["id"]


@pytest.mark.asyncio
async def test_require_strategy_filters_in_sql() -> None:
    executor = _FakeExecutor([])
    await resolve_trigger(executor, workspace_id=_WS, path="a.md", require_strategy=True)
    assert "strategy_id IS NOT NULL" in executor.queries[0]
    await resolve_trigger(executor, workspace_id=_WS, path="a.md")
    assert "strategy_id IS NOT NULL" not in executor.queries[1]
