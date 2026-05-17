from __future__ import annotations

from hashlib import sha256
from typing import Any

import asyncpg
import pytest

from rag.schemas.admin import RerankSpec
from rag.services.rerank_configs import (
    delete_rerank_config,
    get_rerank_config,
    upsert_rerank_config,
)
from tests.integration._workspace_seed import seed_workspace


class _StubResolver:
    """Resolver factice : accept tout, never raises."""

    async def resolve_with_retry(self, ref: str) -> str:
        return "stubbed-secret-value"


class _FailingResolver:
    async def resolve_with_retry(self, ref: str) -> str:
        raise RuntimeError(f"vault ref not found: {ref}")


@pytest.fixture
async def workspace_id(migrated: asyncpg.Pool) -> str:
    async with migrated.acquire() as conn:
        return await seed_workspace(conn, name="ws_rerank")


@pytest.mark.asyncio
async def test_get_returns_none_when_no_config(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    cfg = await get_rerank_config(workspace_id, migrated)
    assert cfg is None


@pytest.mark.asyncio
async def test_upsert_inserts_new_config(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    spec = RerankSpec(
        provider="cohere", model="rerank-v3.5",
        api_key_ref="cohere_key", base_url=None, top_k_pre_rerank=50,
    )
    cfg = await upsert_rerank_config(
        workspace_id=workspace_id, spec=spec,
        config_pool=migrated, resolver=_StubResolver(), default_vault_name="rag",
    )
    assert cfg["provider"] == "cohere"
    assert cfg["model"] == "rerank-v3.5"
    assert cfg["api_key_ref"] == "cohere_key"
    assert cfg["top_k_pre_rerank"] == 50


@pytest.mark.asyncio
async def test_upsert_updates_existing(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    spec1 = RerankSpec(provider="cohere", model="rerank-v3.5",
                       api_key_ref="k1", base_url=None, top_k_pre_rerank=50)
    spec2 = RerankSpec(provider="voyage", model="rerank-2",
                       api_key_ref="k2", base_url=None, top_k_pre_rerank=100)
    await upsert_rerank_config(workspace_id=workspace_id, spec=spec1,
                               config_pool=migrated, resolver=_StubResolver(),
                               default_vault_name="rag")
    cfg = await upsert_rerank_config(workspace_id=workspace_id, spec=spec2,
                                     config_pool=migrated, resolver=_StubResolver(),
                                     default_vault_name="rag")
    assert cfg["provider"] == "voyage"
    assert cfg["model"] == "rerank-2"
    assert cfg["top_k_pre_rerank"] == 100


@pytest.mark.asyncio
async def test_upsert_eager_validates_api_key_ref(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    """Si la ref Harpocrate n'est pas résolvable, upsert lève."""
    spec = RerankSpec(provider="cohere", model="rerank-v3.5",
                     api_key_ref="bad_ref", base_url=None, top_k_pre_rerank=50)
    with pytest.raises(RuntimeError, match="vault ref not found"):
        await upsert_rerank_config(workspace_id=workspace_id, spec=spec,
                                    config_pool=migrated, resolver=_FailingResolver(),
                                    default_vault_name="rag")
    # Vérifie qu'aucune row n'a été créée
    cfg = await get_rerank_config(workspace_id, migrated)
    assert cfg is None


@pytest.mark.asyncio
async def test_upsert_skips_validation_if_no_api_key_ref(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    """Ollama : api_key_ref None → pas d'appel resolver (Failing ne lève donc pas)."""
    spec = RerankSpec(provider="ollama", model="bge",
                     api_key_ref=None, base_url="http://localhost:11434",
                     top_k_pre_rerank=50)
    cfg = await upsert_rerank_config(workspace_id=workspace_id, spec=spec,
                                     config_pool=migrated, resolver=_FailingResolver(),
                                     default_vault_name="rag")
    assert cfg["provider"] == "ollama"


@pytest.mark.asyncio
async def test_delete_removes_config(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    spec = RerankSpec(provider="cohere", model="rerank-v3.5",
                     api_key_ref="k", base_url=None, top_k_pre_rerank=50)
    await upsert_rerank_config(workspace_id=workspace_id, spec=spec,
                               config_pool=migrated, resolver=_StubResolver(),
                               default_vault_name="rag")
    await delete_rerank_config(workspace_id, migrated)
    cfg = await get_rerank_config(workspace_id, migrated)
    assert cfg is None


@pytest.mark.asyncio
async def test_delete_idempotent_when_absent(
    migrated: asyncpg.Pool, workspace_id: str,
) -> None:
    """Pas d'erreur si la config n'existe pas."""
    await delete_rerank_config(workspace_id, migrated)  # ne lève pas
