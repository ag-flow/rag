"""Endpoints de vectorisation portés par les coffres (slug + service)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.schemas.vault_endpoints import (
    EndpointCreate,
    EndpointIndexerSpec,
    EndpointRerankSpec,
    slugify,
)
from rag.services.vault_endpoints import create_endpoint, delete_endpoint


class TestSlugify:
    def test_basic_label(self) -> None:
        assert slugify("Docs OpenAI") == "docs-openai"

    def test_accents_and_symbols(self) -> None:
        assert slugify("Docs internes (Ollama) !") == "docs-internes-ollama"

    def test_collapses_separators(self) -> None:
        assert slugify("  code --- Voyage  ") == "code-voyage"

    def test_empty_result(self) -> None:
        assert slugify("!!!") == ""


def _row(**overrides):
    base = {
        "id": uuid4(),
        "vault_id": uuid4(),
        "label": "Docs OpenAI",
        "slug": "docs-openai",
        "indexer_provider": "openai",
        "indexer_model": "text-embedding-3-small",
        "indexer_api_key_ref": "${vault://rag:/providers/openai}",
        "indexer_base_url": None,
        "rerank_provider": None,
        "rerank_model": None,
        "rerank_api_key_ref": None,
        "rerank_base_url": None,
        "llm_provider": None,
        "llm_model": None,
        "llm_api_key_ref": None,
        "llm_base_url": None,
        "rerank_top_k": None,
        "created_at": datetime(2026, 7, 16, tzinfo=UTC),
        "updated_at": datetime(2026, 7, 16, tzinfo=UTC),
    }
    base.update(overrides)
    return base


class TestCreateEndpoint:
    @pytest.mark.asyncio
    async def test_create_computes_slug_and_maps_row(self) -> None:
        vault_id = uuid4()
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value=_row(vault_id=vault_id))

        req = EndpointCreate(
            label="Docs OpenAI",
            indexer=EndpointIndexerSpec(
                provider="openai",
                model="text-embedding-3-small",
                api_key_ref="${vault://rag:/providers/openai}",
            ),
        )
        out = await create_endpoint(conn, vault_id=vault_id, req=req)

        assert out.slug == "docs-openai"
        assert out.rerank is None
        # Le slug calculé est bien passé à l'INSERT ($3).
        assert conn.fetchrow.await_args.args[3] == "docs-openai"

    @pytest.mark.asyncio
    async def test_create_with_rerank_maps_spec(self) -> None:
        conn = MagicMock()
        conn.fetchrow = AsyncMock(
            return_value=_row(
                rerank_provider="cohere",
                rerank_model="rerank-v3.5",
                rerank_top_k=25,
            )
        )
        req = EndpointCreate(
            label="Docs OpenAI",
            indexer=EndpointIndexerSpec(provider="openai", model="text-embedding-3-small"),
            rerank=EndpointRerankSpec(
                provider="cohere", model="rerank-v3.5", top_k_pre_rerank=25
            ),
        )
        out = await create_endpoint(conn, vault_id=uuid4(), req=req)
        assert out.rerank is not None
        assert out.rerank.provider == "cohere"
        assert out.rerank.top_k_pre_rerank == 25

    @pytest.mark.asyncio
    async def test_create_rejects_unsluggable_label(self) -> None:
        conn = MagicMock()
        req = EndpointCreate(
            label="!!!",
            indexer=EndpointIndexerSpec(provider="openai", model="m"),
        )
        with pytest.raises(ValueError, match="slug"):
            await create_endpoint(conn, vault_id=uuid4(), req=req)


class TestDeleteEndpoint:
    @pytest.mark.asyncio
    async def test_delete_returns_false_when_missing(self) -> None:
        conn = MagicMock()
        conn.execute = AsyncMock(return_value="DELETE 0")
        assert await delete_endpoint(conn, endpoint_id=uuid4()) is False

    @pytest.mark.asyncio
    async def test_delete_returns_true_when_removed(self) -> None:
        conn = MagicMock()
        conn.execute = AsyncMock(return_value="DELETE 1")
        assert await delete_endpoint(conn, endpoint_id=uuid4()) is True
