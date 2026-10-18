"""Refresh depuis l'endpoint et partage (migration 095) : la garde « partage
retiré » se juge pour le PROPRIÉTAIRE du workspace, jamais pour l'appelant."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import rag.services.endpoint_refresh as refresh_mod
from rag.schemas.vault_endpoints import EndpointIndexerSpec, EndpointOut

_OWNER = "c" * 64


class _CopyStartedError(Exception):
    """La garde est franchie : la recopie de configuration a commencé."""


def _endpoint() -> EndpointOut:
    return EndpointOut(
        id=uuid4(),
        vault_id=uuid4(),
        label="ep",
        slug="ep",
        indexer=EndpointIndexerSpec(provider="openai", model="text-embedding-3-small"),
        rerank=None,
        llm=None,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


def _pool(owner_id: str | None) -> MagicMock:
    row = {
        "endpoint_id": uuid4(),
        "owner_id": owner_id,
        "provider": "openai",
        "model": "text-embedding-3-small",
        "api_key_ref": None,
        "base_url": None,
        "rpm_limit": None,
        "tpm_limit": None,
    }
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=row)

    @asynccontextmanager
    async def acquire() -> Any:
        yield MagicMock()

    pool.acquire = acquire
    return pool


async def _refresh(pool: MagicMock) -> Any:
    return await refresh_mod.refresh_workspace_from_endpoint(
        workspace_id=uuid4(),
        workspace_name="ws",
        confirm=False,
        config_pool=pool,
        admin_dsn="postgresql://x",
        resolver=MagicMock(),
        default_vault_name="rag",
    )


@pytest.mark.asyncio
async def test_refresh_of_owned_workspace_with_unshared_endpoint_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(refresh_mod, "get_endpoint", AsyncMock(return_value=_endpoint()))
    usable = AsyncMock(return_value=None)
    monkeypatch.setattr(refresh_mod, "db_get_usable_endpoint", usable)

    with pytest.raises(refresh_mod.EndpointNotUsableError):
        await _refresh(_pool(_OWNER))
    assert usable.await_args.kwargs["owner_id"] == _OWNER


@pytest.mark.asyncio
async def test_refresh_of_shared_workspace_skips_the_sharing_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workspace partagé (owner NULL) : aucun bénéficiaire, pas de garde — la
    recopie démarre (sentinelle levée par sa première écriture)."""
    monkeypatch.setattr(refresh_mod, "get_endpoint", AsyncMock(return_value=_endpoint()))
    usable = AsyncMock(return_value=None)
    monkeypatch.setattr(refresh_mod, "db_get_usable_endpoint", usable)
    monkeypatch.setattr(
        refresh_mod, "delete_rerank_config", AsyncMock(side_effect=_CopyStartedError)
    )

    with pytest.raises(_CopyStartedError):
        await _refresh(_pool(None))
    usable.assert_not_awaited()
