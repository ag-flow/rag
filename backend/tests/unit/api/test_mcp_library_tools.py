from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.api.mcp_library_tools import register_library_tools
from rag.api.mcp_standard import RagMcpDispatcher, _KeyCtx, _ws_ctx
from rag.schemas.chunking_strategies import StrategyDetailOut
from rag.schemas.enrichments import PromptTemplateOut
from rag.services import chunking_strategies as strategies_svc
from rag.services import prompt_templates as templates_svc


class FakeMCP:
    """Enregistreur minimal : capture les outils décorés par @mcp.tool()."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self) -> Any:
        def deco(fn: Any) -> Any:
            self.tools[fn.__name__] = fn
            return fn

        return deco


class _FakePool:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def acquire(self) -> Any:
        conn = self._conn

        class _CM:
            async def __aenter__(self) -> Any:
                return conn

            async def __aexit__(self, *args: Any) -> bool:
                return False

        return _CM()


def _make_ctx(*, scope: str = "admin", owner_id: str = "owner-1") -> _KeyCtx:
    return _KeyCtx(
        owner_id=owner_id,
        scope=scope,
        config_pool=_FakePool(MagicMock()),
        pool_registry=MagicMock(),
        resolver=MagicMock(),
        client_provider=MagicMock(),
        default_vault_name=None,
    )


def _detail_out(**over: Any) -> StrategyDetailOut:
    base: dict[str, Any] = dict(
        id=uuid4(),
        label="Docs",
        slug="docs",
        algo="prose",
        params={},
        parser_slug=None,
        is_system=False,
        used_by_routes=0,
        used_by_categories=0,
        used_by_triggers=0,
        used_by_workspaces=0,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
        routes=[],
        prompts=[],
    )
    base.update(over)
    return StrategyDetailOut(**base)


def _template_out(**over: Any) -> PromptTemplateOut:
    base: dict[str, Any] = dict(
        id=uuid4(),
        name="ctx-chunk",
        language="markdown",
        description=None,
        metadata_key="context",
        result_type="text",
        result_schema=None,
        prompt="Résume ce chunk.",
        target="chunk",
        timing="embedding_inline",
        prompt_version=1,
        is_system=False,
        used_by_triggers=0,
        used_by_strategies=0,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    base.update(over)
    return PromptTemplateOut(**base)


@pytest.fixture
def tools() -> dict[str, Any]:
    mcp = FakeMCP()
    register_library_tools(mcp, _ws_ctx)
    return mcp.tools


async def _call(tool: Any, ctx: _KeyCtx, /, **kwargs: Any) -> str:
    token = _ws_ctx.set(ctx)
    try:
        return await tool(**kwargs)
    finally:
        _ws_ctx.reset(token)


# ── Garde d'écriture (niveau admin requis) ───────────────────────────────────


class TestWriteGuard:
    @pytest.mark.asyncio
    async def test_create_strategy_refused_for_non_admin(self, tools, monkeypatch):
        create = AsyncMock()
        monkeypatch.setattr(strategies_svc, "create_strategy", create)
        result = await _call(
            tools["create_chunking_strategy"],
            _make_ctx(scope="read_write"),
            label="Docs",
            algo="prose",
        )
        assert "admin" in result
        assert "refusé" in result.lower()
        create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_template_refused_for_non_admin(self, tools, monkeypatch):
        create = AsyncMock()
        monkeypatch.setattr(templates_svc, "create_prompt_template", create)
        result = await _call(
            tools["create_prompt_template"],
            _make_ctx(scope="read"),
            name="t",
            language="md",
            metadata_key="k",
            prompt="p",
            mode="chunk",
        )
        assert "admin" in result
        create.assert_not_awaited()


# ── Stratégies ───────────────────────────────────────────────────────────────


class TestStrategyTools:
    @pytest.mark.asyncio
    async def test_create_calls_service_with_ctx_owner_id(self, tools, monkeypatch):
        create = AsyncMock(return_value=_detail_out())
        monkeypatch.setattr(strategies_svc, "create_strategy", create)
        result = await _call(
            tools["create_chunking_strategy"],
            _make_ctx(owner_id="owner-42"),
            label="Docs internes",
            algo="prose",
            params={"child_target_tokens": 256},
        )
        assert create.await_args.kwargs["owner_id"] == "owner-42"
        req = create.await_args.kwargs["req"]
        assert req.label == "Docs internes"
        assert req.params == {"child_target_tokens": 256}
        assert '"slug": "docs"' in result

    @pytest.mark.asyncio
    async def test_create_slug_conflict_returns_message(self, tools, monkeypatch):
        monkeypatch.setattr(
            strategies_svc,
            "create_strategy",
            AsyncMock(side_effect=strategies_svc.StrategySlugConflictError("docs")),
        )
        result = await _call(
            tools["create_chunking_strategy"], _make_ctx(), label="Docs", algo="prose"
        )
        assert "docs" in result
        assert "déjà utilisé" in result.lower()

    @pytest.mark.asyncio
    async def test_create_invalid_algo_returns_message(self, tools, monkeypatch):
        create = AsyncMock()
        monkeypatch.setattr(strategies_svc, "create_strategy", create)
        result = await _call(
            tools["create_chunking_strategy"], _make_ctx(), label="X", algo="magic"
        )
        assert "magic" in result
        create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_in_use_returns_counts_message(self, tools, monkeypatch):
        monkeypatch.setattr(
            strategies_svc,
            "delete_strategy",
            AsyncMock(
                side_effect=strategies_svc.StrategyInUseError(
                    used_by_routes=2,
                    used_by_categories=0,
                    used_by_triggers=1,
                    used_by_workspaces=0,
                )
            ),
        )
        result = await _call(
            tools["delete_chunking_strategy"], _make_ctx(), strategy_id=str(uuid4())
        )
        assert "refusée" in result.lower()
        assert "2 route" in result

    @pytest.mark.asyncio
    async def test_get_invalid_uuid_returns_message(self, tools):
        result = await _call(tools["get_chunking_strategy"], _make_ctx(), strategy_id="pas-un-uuid")
        assert "invalide" in result.lower()

    @pytest.mark.asyncio
    async def test_system_immutable_returns_message(self, tools, monkeypatch):
        monkeypatch.setattr(
            strategies_svc,
            "patch_strategy",
            AsyncMock(side_effect=strategies_svc.StrategyImmutableError("id")),
        )
        result = await _call(
            tools["update_chunking_strategy"],
            _make_ctx(),
            strategy_id=str(uuid4()),
            label="Nouveau",
        )
        assert "système" in result.lower()
        assert "duplicate_chunking_strategy" in result

    @pytest.mark.asyncio
    async def test_update_remove_parser_marks_field_set(self, tools, monkeypatch):
        patch = AsyncMock(return_value=_detail_out())
        monkeypatch.setattr(strategies_svc, "patch_strategy", patch)
        await _call(
            tools["update_chunking_strategy"],
            _make_ctx(),
            strategy_id=str(uuid4()),
            remove_parser=True,
        )
        req = patch.await_args.kwargs["req"]
        assert "parser_slug" in req.model_fields_set
        assert req.parser_slug is None

    @pytest.mark.asyncio
    async def test_update_without_parser_leaves_field_unset(self, tools, monkeypatch):
        patch = AsyncMock(return_value=_detail_out())
        monkeypatch.setattr(strategies_svc, "patch_strategy", patch)
        await _call(
            tools["update_chunking_strategy"],
            _make_ctx(),
            strategy_id=str(uuid4()),
            label="Renommée",
        )
        req = patch.await_args.kwargs["req"]
        assert "parser_slug" not in req.model_fields_set

    @pytest.mark.asyncio
    async def test_set_routes_duplicate_pair_returns_message(self, tools, monkeypatch):
        set_routes = AsyncMock()
        monkeypatch.setattr(strategies_svc, "set_region_routes", set_routes)
        result = await _call(
            tools["set_chunking_strategy_routes"],
            _make_ctx(),
            strategy_id=str(uuid4()),
            routes=[
                {"region_type": "code_fence", "qualifier": "mermaid"},
                {"region_type": "code_fence", "qualifier": "mermaid"},
            ],
        )
        assert "double" in result.lower()
        set_routes.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_set_prompts_passes_specs_to_service(self, tools, monkeypatch):
        set_prompts = AsyncMock(return_value=[])
        monkeypatch.setattr(strategies_svc, "set_strategy_prompts", set_prompts)
        template_id = uuid4()
        await _call(
            tools["set_chunking_strategy_prompts"],
            _make_ctx(owner_id="owner-9"),
            strategy_id=str(uuid4()),
            prompts=[{"template_id": str(template_id), "order_index": 2}],
        )
        assert set_prompts.await_args.kwargs["owner_id"] == "owner-9"
        specs = set_prompts.await_args.kwargs["prompts"]
        assert specs[0].template_id == template_id
        assert specs[0].order_index == 2
        assert specs[0].enabled is True

    @pytest.mark.asyncio
    async def test_duplicate_calls_service_with_label(self, tools, monkeypatch):
        dup = AsyncMock(return_value=_detail_out(label="Copie", slug="copie"))
        monkeypatch.setattr(strategies_svc, "duplicate_strategy", dup)
        source_id = uuid4()
        result = await _call(
            tools["duplicate_chunking_strategy"],
            _make_ctx(),
            strategy_id=str(source_id),
            label="Copie",
        )
        assert dup.await_args.kwargs["source_id"] == source_id
        assert dup.await_args.kwargs["label"] == "Copie"
        assert "Copie" in result


# ── Templates de prompts ─────────────────────────────────────────────────────


class TestPromptTemplateTools:
    @pytest.mark.asyncio
    async def test_mode_document_derives_axes(self, tools, monkeypatch):
        create = AsyncMock(return_value=_template_out())
        monkeypatch.setattr(templates_svc, "create_prompt_template", create)
        await _call(
            tools["create_prompt_template"],
            _make_ctx(),
            name="résumé",
            language="markdown",
            metadata_key="summary",
            prompt="Résume.",
            mode="document",
        )
        req = create.await_args.kwargs["req"]
        assert req.target == "document"
        assert req.timing == "post_index_metadata"

    @pytest.mark.asyncio
    async def test_mode_region_derives_qualified_target(self, tools, monkeypatch):
        create = AsyncMock(return_value=_template_out())
        monkeypatch.setattr(templates_svc, "create_prompt_template", create)
        await _call(
            tools["create_prompt_template"],
            _make_ctx(owner_id="owner-7"),
            name="mermaid-ctx",
            language="markdown",
            metadata_key="diagram_context",
            prompt="Décris le diagramme.",
            mode="region",
            region_type="code_fence",
            region_qualifier="mermaid",
        )
        assert create.await_args.kwargs["owner_id"] == "owner-7"
        req = create.await_args.kwargs["req"]
        assert req.target == "region:code_fence:mermaid"
        assert req.timing == "embedding_inline"

    @pytest.mark.asyncio
    async def test_mode_region_without_type_returns_message(self, tools, monkeypatch):
        create = AsyncMock()
        monkeypatch.setattr(templates_svc, "create_prompt_template", create)
        result = await _call(
            tools["create_prompt_template"],
            _make_ctx(),
            name="t",
            language="md",
            metadata_key="k",
            prompt="p",
            mode="region",
        )
        assert "region_type" in result
        create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_mode_returns_message(self, tools):
        result = await _call(
            tools["create_prompt_template"],
            _make_ctx(),
            name="t",
            language="md",
            metadata_key="k",
            prompt="p",
            mode="inline",
        )
        assert "mode" in result.lower()
        assert "document" in result

    @pytest.mark.asyncio
    async def test_delete_in_use_returns_message(self, tools, monkeypatch):
        monkeypatch.setattr(
            templates_svc,
            "delete_prompt_template",
            AsyncMock(side_effect=templates_svc.TemplateInUseError(3)),
        )
        result = await _call(tools["delete_prompt_template"], _make_ctx(), template_id=str(uuid4()))
        assert "refusée" in result.lower()
        assert "3" in result

    @pytest.mark.asyncio
    async def test_update_passes_patch_fields(self, tools, monkeypatch):
        patch = AsyncMock(return_value=_template_out())
        monkeypatch.setattr(templates_svc, "patch_prompt_template", patch)
        await _call(
            tools["update_prompt_template"],
            _make_ctx(),
            template_id=str(uuid4()),
            prompt="Nouveau prompt.",
        )
        req = patch.await_args.kwargs["req"]
        assert req.prompt == "Nouveau prompt."
        assert req.description is None


# ── Dispatcher : contexte étendu ─────────────────────────────────────────────


class TestLoadContextGrants:
    @pytest.mark.asyncio
    async def test_load_context_exposes_owner_id_and_scope(self):
        dispatcher = RagMcpDispatcher(AsyncMock())
        row = {"owner_id": "owner-abc", "scope": "admin"}
        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value=row)
        dispatcher._config_pool = pool
        dispatcher._pool_registry = MagicMock()
        dispatcher._resolver = MagicMock()
        dispatcher._client_provider = None

        ctx = await dispatcher._load_context("tok")

        assert ctx.owner_id == "owner-abc"
        assert ctx.scope == "admin"
        sql = pool.fetchrow.await_args.args[0]
        assert "owner_id" in sql
        assert "scope" in sql
        assert "user_api_keys" in sql
