from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from rag.services.chunking_preview import (
    PreviewStrategyNotFoundError,
    compare_strategies,
    preview_strategy,
)

_DOC = """# Guide

Un paragraphe de prose qui explique le fonctionnement.

```mermaid
graph TD; A-->B;
```

Encore de la prose après le diagramme.
"""


class _FakePool:
    """Pool minimal : fetchrow direct + acquire() pour le builder de chunker."""

    def __init__(
        self,
        strategies: dict[Any, dict[str, Any]],
        routes: dict[Any, list[dict[str, Any]]],
    ) -> None:
        self._strategies = strategies
        self._routes = routes

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        strategy_id = args[-1]
        return self._strategies.get(strategy_id)

    def acquire(self) -> _FakePool._Ctx:
        return _FakePool._Ctx(self)

    class _Ctx:
        def __init__(self, pool: _FakePool) -> None:
            self._pool = pool

        async def __aenter__(self) -> _FakePool._Conn:
            return _FakePool._Conn(self._pool)

        async def __aexit__(self, *exc: object) -> None:
            return None

    class _Conn:
        def __init__(self, pool: _FakePool) -> None:
            self._pool = pool

        async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
            return self._pool._strategies.get(args[0])

        async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
            return self._pool._routes.get(args[0], [])


def _strategy_row(
    strategy_id: Any, *, parser_slug: str | None = None, algo: str = "prose"
) -> dict[str, Any]:
    return {
        "id": strategy_id,
        "label": "Ma stratégie",
        "slug": "ma-strategie",
        "algo": algo,
        "params": "{}",
        "parser_slug": parser_slug,
    }


@pytest.mark.asyncio
async def test_preview_plain_strategy_returns_chunks_and_totals() -> None:
    sid = uuid4()
    pool = _FakePool({sid: _strategy_row(sid)}, {})
    result = await preview_strategy(
        pool,  # type: ignore[arg-type]
        owner_id="0" * 64,
        strategy_id=sid,
        content=_DOC,
    )
    assert result.strategy.slug == "ma-strategie"
    assert result.total_chunks == len(result.chunks) > 0
    assert result.total_tokens == sum(c.tokens for c in result.chunks)
    assert result.regions == []  # pas de parser → pas de passe régions
    assert all(c.chunk_hash for c in result.chunks)


@pytest.mark.asyncio
async def test_preview_parent_only_region_excluded_and_reported() -> None:
    sid = uuid4()
    routes = [
        {
            "region_type": "code_fence",
            "qualifier": "mermaid",
            "target_strategy_id": None,
            "atomic": False,
            "overflow_policy": "parent_only",
        }
    ]
    pool = _FakePool({sid: _strategy_row(sid, parser_slug="markdown")}, {sid: routes})
    result = await preview_strategy(
        pool,  # type: ignore[arg-type]
        owner_id="0" * 64,
        strategy_id=sid,
        content=_DOC,
    )
    # La fence mermaid n'est jamais embeddée…
    assert all("graph TD" not in c.embed_text for c in result.chunks)
    # …mais la région est rapportée avec sa politique.
    mermaid = next(r for r in result.regions if r.qualifier == "mermaid")
    assert (mermaid.routed, mermaid.overflow_policy) == (True, "parent_only")
    prose_regions = [r for r in result.regions if r.region_type == "prose"]
    assert all(not r.routed for r in prose_regions)


@pytest.mark.asyncio
async def test_preview_unknown_strategy_raises() -> None:
    pool = _FakePool({}, {})
    with pytest.raises(PreviewStrategyNotFoundError):
        await preview_strategy(
            pool,  # type: ignore[arg-type]
            owner_id="0" * 64,
            strategy_id=uuid4(),
            content="# Doc",
        )


@pytest.mark.asyncio
async def test_compare_same_strategy_yields_empty_diff() -> None:
    sid = uuid4()
    pool = _FakePool({sid: _strategy_row(sid)}, {})
    result = await compare_strategies(
        pool,  # type: ignore[arg-type]
        owner_id="0" * 64,
        content=_DOC,
        strategy_a=sid,
        strategy_b=sid,
    )
    assert result.diff.only_a == result.diff.only_b == []
    assert result.diff.common == len({c.chunk_hash for c in result.a.chunks})
