from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.api.mcp_endpoint_tools import ENDPOINT_ADMIN_REFUSAL, register_endpoint_tools
from rag.api.mcp_standard import _KeyCtx, _ws_ctx
from rag.schemas.vault_endpoints import (
    EndpointIndexerSpec,
    EndpointOut,
    EndpointRerankSpec,
)
from rag.services import vault_endpoints as endpoints_svc


class FakeMCP:
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


_OWNER = "a" * 64


def _make_ctx(conn: Any, *, scope: str = "admin", owner_id: str = _OWNER) -> _KeyCtx:
    return _KeyCtx(
        owner_id=owner_id,
        scope=scope,
        config_pool=_FakePool(conn),
        pool_registry=MagicMock(),
        resolver=MagicMock(),
        client_provider=MagicMock(),
        default_vault_name=None,
    )


def _vault_row(*, name: str = "coffre-a", owner_id: str = _OWNER, is_default: bool = False):
    return {
        "id": uuid4(),
        "name": name,
        "label": name.title(),
        "is_default": is_default,
        "owner_id": owner_id,
    }


def _endpoint_out(*, slug: str = "azure-prod", with_rerank: bool = True) -> EndpointOut:
    return EndpointOut(
        id=uuid4(),
        vault_id=uuid4(),
        label=slug.title(),
        slug=slug,
        indexer=EndpointIndexerSpec(provider="openai", model="text-embedding-3-small"),
        rerank=(
            EndpointRerankSpec(provider="cohere", model="rerank-v4.0", top_k_pre_rerank=30)
            if with_rerank
            else None
        ),
        llm=None,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


def _register(conn: Any, *, scope: str = "admin", owner_id: str = _OWNER) -> dict[str, Any]:
    mcp = FakeMCP()
    register_endpoint_tools(mcp, _ws_ctx)
    _ws_ctx.set(_make_ctx(conn, scope=scope, owner_id=owner_id))
    return mcp.tools


@pytest.mark.asyncio
async def test_list_endpoints_requires_admin() -> None:
    tools = _register(MagicMock(), scope="read_write")
    assert await tools["list_endpoints"]() == ENDPOINT_ADMIN_REFUSAL


@pytest.mark.asyncio
async def test_list_endpoints_groups_by_vault_with_writable_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    own = _vault_row(name="coffre-a")
    shared = _vault_row(name="commun", owner_id="", is_default=True)
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[own, shared])
    monkeypatch.setattr(endpoints_svc, "list_endpoints", AsyncMock(return_value=[_endpoint_out()]))
    tools = _register(conn)

    payload = json.loads(await tools["list_endpoints"]())

    assert [v["vault"] for v in payload] == ["coffre-a", "commun"]
    assert payload[0]["writable"] is True
    assert payload[1]["writable"] is False
    assert payload[0]["endpoints"][0]["services"]["rerank"] == {
        "provider": "cohere",
        "model": "rerank-v4.0",
    }


@pytest.mark.asyncio
async def test_get_endpoint_configuration_exposes_quotas_not_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = _vault_row()
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=vault)
    monkeypatch.setattr(endpoints_svc, "list_endpoints", AsyncMock(return_value=[_endpoint_out()]))
    tools = _register(conn)

    payload = json.loads(await tools["get_endpoint_configuration"]("coffre-a", "azure-prod"))

    assert payload["slug"] == "azure-prod"
    assert payload["rerank"]["top_k_pre_rerank"] == 30
    assert "rpm_limit" in payload["indexer"]
    assert "id" not in payload
    assert "vault_id" not in payload


@pytest.mark.asyncio
async def test_get_endpoint_configuration_unknown_vault() -> None:
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=None)
    tools = _register(conn)

    out = await tools["get_endpoint_configuration"]("inconnu", "azure-prod")

    assert "introuvable" in out


@pytest.mark.asyncio
async def test_configure_refused_on_foreign_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    shared = _vault_row(name="commun", owner_id="", is_default=True)
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=shared)
    tools = _register(conn)

    out = await tools["configure_endpoint_service"]("commun", "azure-prod", "rerank", model="x")

    assert "lecture seule" in out


@pytest.mark.asyncio
async def test_configure_merges_partial_update(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _vault_row()
    current = _endpoint_out()
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=vault)
    monkeypatch.setattr(endpoints_svc, "list_endpoints", AsyncMock(return_value=[current]))
    update_mock = AsyncMock(return_value=current)
    monkeypatch.setattr(endpoints_svc, "update_endpoint", update_mock)
    tools = _register(conn)

    out = await tools["configure_endpoint_service"](
        "coffre-a", "azure-prod", "rerank", top_k_pre_rerank=50
    )

    req = update_mock.call_args.kwargs["req"]
    assert req.rerank is not None
    assert req.rerank.top_k_pre_rerank == 50
    # Champs omis conservés depuis la config courante.
    assert req.rerank.provider == "cohere"
    assert req.rerank.model == "rerank-v4.0"
    assert "Snapshot" in out


@pytest.mark.asyncio
async def test_configure_new_section_requires_provider_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = _vault_row()
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=vault)
    monkeypatch.setattr(endpoints_svc, "list_endpoints", AsyncMock(return_value=[_endpoint_out()]))
    tools = _register(conn)

    out = await tools["configure_endpoint_service"](
        "coffre-a", "azure-prod", "llm", base_url="http://ollama:11434"
    )

    assert "provider" in out and "model" in out


@pytest.mark.asyncio
async def test_configure_clear_vectorization_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _vault_row()
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=vault)
    monkeypatch.setattr(endpoints_svc, "list_endpoints", AsyncMock(return_value=[_endpoint_out()]))
    tools = _register(conn)

    out = await tools["configure_endpoint_service"](
        "coffre-a", "azure-prod", "vectorization", clear=True
    )

    assert "obligatoire" in out


@pytest.mark.asyncio
async def test_configure_unknown_service() -> None:
    tools = _register(MagicMock())

    out = await tools["configure_endpoint_service"]("coffre-a", "azure-prod", "embedding")

    assert "Service inconnu" in out


@pytest.mark.asyncio
async def test_set_fallback_resolves_slug_to_id(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _vault_row()
    primary = _endpoint_out(slug="azure-prod")
    mirror = _endpoint_out(slug="ollama-mirror")
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=vault)
    monkeypatch.setattr(endpoints_svc, "list_endpoints", AsyncMock(return_value=[primary, mirror]))
    update_mock = AsyncMock(return_value=primary)
    monkeypatch.setattr(endpoints_svc, "update_endpoint", update_mock)
    tools = _register(conn)

    out = await tools["set_endpoint_fallback"](
        "coffre-a", "azure-prod", "ollama-mirror", failure_threshold=5
    )

    req = update_mock.call_args.kwargs["req"]
    assert req.fallback_endpoint_id == mirror.id
    assert req.clear_fallback is False
    assert req.failure_threshold == 5
    payload = json.loads(out)
    assert payload["fallback"] == "ollama-mirror"


@pytest.mark.asyncio
async def test_set_fallback_empty_string_clears(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _vault_row()
    primary = _endpoint_out(slug="azure-prod")
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=vault)
    monkeypatch.setattr(endpoints_svc, "list_endpoints", AsyncMock(return_value=[primary]))
    update_mock = AsyncMock(return_value=primary)
    monkeypatch.setattr(endpoints_svc, "update_endpoint", update_mock)
    tools = _register(conn)

    out = await tools["set_endpoint_fallback"]("coffre-a", "azure-prod", "")

    req = update_mock.call_args.kwargs["req"]
    assert req.clear_fallback is True
    assert req.fallback_endpoint_id is None
    assert json.loads(out)["fallback"] is None


@pytest.mark.asyncio
async def test_set_fallback_unknown_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _vault_row()
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=vault)
    monkeypatch.setattr(endpoints_svc, "list_endpoints", AsyncMock(return_value=[_endpoint_out()]))
    tools = _register(conn)

    out = await tools["set_endpoint_fallback"]("coffre-a", "azure-prod", "inexistant")

    assert "introuvable" in out


@pytest.mark.asyncio
async def test_set_fallback_service_refusal_is_pedagogical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rag.services.endpoint_fallback import EndpointFallbackInvalidError

    vault = _vault_row()
    primary = _endpoint_out(slug="azure-prod")
    mirror = _endpoint_out(slug="autre-modele")
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=vault)
    monkeypatch.setattr(endpoints_svc, "list_endpoints", AsyncMock(return_value=[primary, mirror]))
    monkeypatch.setattr(
        endpoints_svc,
        "update_endpoint",
        AsyncMock(side_effect=EndpointFallbackInvalidError("vectorisation incompatible : x")),
    )
    tools = _register(conn)

    out = await tools["set_endpoint_fallback"]("coffre-a", "azure-prod", "autre-modele")

    assert out.startswith("Fallback refusé")
    assert "vectorisation incompatible" in out
