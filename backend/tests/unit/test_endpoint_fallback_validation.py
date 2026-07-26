"""Gardes d'écriture du fallback d'endpoint (enabler f94bfd84) : un seul
niveau, même coffre, compatibilité de vectorisation (même modèle/dimension)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from rag.services.endpoint_fallback import EndpointFallbackInvalidError, validate_fallback

_VAULT = uuid4()
_PRIMARY = uuid4()
_FALLBACK = uuid4()


def _fb_row(
    *,
    vault_id: Any = _VAULT,
    fallback_endpoint_id: Any = None,
    indexer_provider: str = "azure-openai",
    indexer_model: str = "text-embedding-3-large",
) -> dict[str, Any]:
    return {
        "vault_id": vault_id,
        "fallback_endpoint_id": fallback_endpoint_id,
        "indexer_provider": indexer_provider,
        "indexer_model": indexer_model,
    }


def _conn(
    *,
    fb_row: dict[str, Any] | None,
    referenced: int = 0,
    dimensions: tuple[int | None, int | None] = (3072, 3072),
) -> SimpleNamespace:
    return SimpleNamespace(
        fetchrow=AsyncMock(return_value=fb_row),
        fetchval=AsyncMock(side_effect=[referenced, *dimensions]),
    )


async def _validate(conn: Any, *, fallback_id: Any = _FALLBACK) -> None:
    await validate_fallback(
        conn,
        endpoint_id=_PRIMARY,
        vault_id=_VAULT,
        fallback_id=fallback_id,
        indexer_provider="openai",
        indexer_model="text-embedding-3-large",
    )


class TestValidateFallback:
    @pytest.mark.asyncio
    async def test_same_model_other_provider_accepted(self) -> None:
        await _validate(_conn(fb_row=_fb_row()))

    @pytest.mark.asyncio
    async def test_self_reference_refused(self) -> None:
        with pytest.raises(EndpointFallbackInvalidError, match="propre fallback"):
            await _validate(_conn(fb_row=_fb_row()), fallback_id=_PRIMARY)

    @pytest.mark.asyncio
    async def test_unknown_fallback_refused(self) -> None:
        with pytest.raises(EndpointFallbackInvalidError, match="introuvable"):
            await _validate(_conn(fb_row=None))

    @pytest.mark.asyncio
    async def test_other_vault_refused(self) -> None:
        with pytest.raises(EndpointFallbackInvalidError, match="même coffre"):
            await _validate(_conn(fb_row=_fb_row(vault_id=uuid4())))

    @pytest.mark.asyncio
    async def test_fallback_with_own_fallback_refused(self) -> None:
        with pytest.raises(EndpointFallbackInvalidError, match="un seul niveau"):
            await _validate(_conn(fb_row=_fb_row(fallback_endpoint_id=uuid4())))

    @pytest.mark.asyncio
    async def test_endpoint_already_used_as_fallback_refused(self) -> None:
        with pytest.raises(EndpointFallbackInvalidError, match="déjà le fallback"):
            await _validate(_conn(fb_row=_fb_row(), referenced=1))

    @pytest.mark.asyncio
    async def test_different_embedding_model_refused(self) -> None:
        row = _fb_row(indexer_model="text-embedding-3-small")
        with pytest.raises(EndpointFallbackInvalidError, match="même modèle"):
            await _validate(_conn(fb_row=row))

    @pytest.mark.asyncio
    async def test_different_declared_dimensions_refused(self) -> None:
        with pytest.raises(EndpointFallbackInvalidError, match="dimensions"):
            await _validate(_conn(fb_row=_fb_row(), dimensions=(3072, 1536)))

    @pytest.mark.asyncio
    async def test_unknown_dimension_tolerated(self) -> None:
        # Modèle absent du registre : la règle porte alors sur le nom du modèle.
        await _validate(_conn(fb_row=_fb_row(), dimensions=(None, 1536)))
