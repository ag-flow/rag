from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from rag.services.chunking_routing import resolve_strategy_for_file

_WS = uuid4()


def _row(strategy_id: UUID, slug: str, algo: str = "prose") -> dict[str, Any]:
    return {"id": strategy_id, "slug": slug, "algo": algo, "params": {}, "parser_slug": None}


class _FakePool:
    """Simule le pool config : triggers (fetch, patterns glob), tables de
    routage (fetch via acquire) et catalogue de stratégies (fetchrow)."""

    def __init__(
        self,
        *,
        strategies: list[dict[str, Any]],
        trigger_bindings: dict[str, UUID] | None = None,
        extension_categories: dict[str, str] | None = None,
        category_strategies: dict[str, str] | None = None,
    ) -> None:
        self._strategies = strategies
        # pattern glob → strategy_id (contrat post-migration 089)
        self._triggers = trigger_bindings or {}
        self._ext = extension_categories if extension_categories is not None else {".py": "code"}
        self._cat = (
            category_strategies
            if category_strategies is not None
            else {"prose": "markdown-deep", "code": "code-aware"}
        )

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        assert "workspace_extension_triggers" in query
        return [
            {"id": uuid4(), "pattern": pattern, "strategy_id": sid}
            for pattern, sid in self._triggers.items()
        ]

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

        async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
            if "chunking_extension_categories" in query:
                return [
                    {"workspace_id": None, "extension": ext, "category": cat}
                    for ext, cat in self._pool._ext.items()
                ]
            assert "chunking_category_strategies" in query
            return [
                {"workspace_id": None, "category": cat, "strategy_name": slug}
                for cat, slug in self._pool._cat.items()
            ]

        async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
            if "WHERE id = $1" in query:
                return next((s for s in self._pool._strategies if s["id"] == args[0]), None)
            return next((s for s in self._pool._strategies if s["slug"] == args[0]), None)


@pytest.mark.asyncio
async def test_explicit_push_binding_wins() -> None:
    bound = uuid4()
    pool = _FakePool(
        strategies=[_row(bound, "poussee")],
        trigger_bindings={"**/*.md": uuid4()},  # ne doit même pas être consulté
    )
    record = await resolve_strategy_for_file(
        pool,  # type: ignore[arg-type]
        workspace_id=_WS,
        path="doc.md",
        strategy_id=bound,
        default_strategy_id=uuid4(),
    )
    assert record.id == bound


@pytest.mark.asyncio
async def test_trigger_binding_beats_cascade_and_default() -> None:
    trigger_target = uuid4()
    default = uuid4()
    pool = _FakePool(
        strategies=[_row(trigger_target, "via-trigger"), _row(default, "defaut-ws")],
        trigger_bindings={"**/*.md": trigger_target},
    )
    record = await resolve_strategy_for_file(
        pool,  # type: ignore[arg-type]
        workspace_id=_WS,
        path="docs/readme.md",
        default_strategy_id=default,
    )
    assert record.slug == "via-trigger"


@pytest.mark.asyncio
async def test_most_specific_trigger_pattern_wins() -> None:
    generic = uuid4()
    backlog = uuid4()
    default = uuid4()
    pool = _FakePool(
        strategies=[
            _row(generic, "generique"),
            _row(backlog, "backlog-dedie"),
            _row(default, "defaut-ws"),
        ],
        trigger_bindings={"**/*.md": generic, "backlog/**/*.md": backlog},
    )
    record = await resolve_strategy_for_file(
        pool,  # type: ignore[arg-type]
        workspace_id=_WS,
        path="backlog/2026/tache.md",
        default_strategy_id=default,
    )
    assert record.slug == "backlog-dedie"


@pytest.mark.asyncio
async def test_workspace_default_replaces_default_category_only() -> None:
    default = uuid4()
    code_aware = uuid4()
    pool = _FakePool(
        strategies=[_row(default, "defaut-ws"), _row(code_aware, "code-aware", algo="code")],
    )
    # .md → catégorie par défaut ('prose') → défaut workspace lié par id.
    md = await resolve_strategy_for_file(
        pool,  # type: ignore[arg-type]
        workspace_id=_WS,
        path="doc.md",
        default_strategy_id=default,
    )
    assert md.slug == "defaut-ws"
    # extension inconnue → catégorie par défaut → défaut workspace aussi.
    unknown = await resolve_strategy_for_file(
        pool,  # type: ignore[arg-type]
        workspace_id=_WS,
        path="LICENCE.xyz",
        default_strategy_id=default,
    )
    assert unknown.slug == "defaut-ws"
    # .py → catégorie spécialisée 'code' → cascade textuelle inchangée.
    py = await resolve_strategy_for_file(
        pool,  # type: ignore[arg-type]
        workspace_id=_WS,
        path="src/main.py",
        default_strategy_id=default,
    )
    assert py.slug == "code-aware"


@pytest.mark.asyncio
async def test_without_bindings_textual_cascade_unchanged() -> None:
    markdown_deep = uuid4()
    pool = _FakePool(strategies=[_row(markdown_deep, "markdown-deep")])
    record = await resolve_strategy_for_file(
        pool,  # type: ignore[arg-type]
        workspace_id=_WS,
        path="doc.md",
    )
    assert record.slug == "markdown-deep"
