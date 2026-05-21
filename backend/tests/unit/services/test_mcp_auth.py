from __future__ import annotations

# Tests unitaires pour _authenticate et _load_workspace_context (T1).
# NOTE(T6): _authenticate n'utilise plus le cache -- lookup DB direct.
# Les tests de cache-hit seront reecrits en T6.
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from rag.api.errors import WorkspaceNotFound
from rag.auth.workspace_auth import ApiKeyCache
from rag.services.mcp import McpWorkspaceRef, _authenticate, _load_workspace_context

_DEK = "x" * 32


@pytest.mark.asyncio
async def test_authenticate_workspace_not_found_raises_error() -> None:
    """Workspace inconnu (premier SELECT None) -> WorkspaceNotFound."""
    cache = ApiKeyCache()
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)

    ref = McpWorkspaceRef(name="ghost", api_key="x")
    with pytest.raises(WorkspaceNotFound):
        await _authenticate(ref=ref, config_pool=pool, apikey_cache=cache, api_key_dek=_DEK)


@pytest.mark.asyncio
async def test_authenticate_bad_key_raises_401() -> None:
    """Fingerprint non trouve (deuxieme SELECT None) -> 401."""
    cache = ApiKeyCache()
    ws_id = uuid4()
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        side_effect=[
            {"id": ws_id, "indexer_used": "openai/m"},
            None,
        ]
    )

    ref = McpWorkspaceRef(name="ws", api_key="wrong-key")
    with pytest.raises(HTTPException) as exc:
        await _authenticate(ref=ref, config_pool=pool, apikey_cache=cache, api_key_dek=_DEK)
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_workspace_apikey"


@pytest.mark.asyncio
async def test_authenticate_valid_key_returns_entry() -> None:
    """Cle valide -> _CacheEntry retourne avec workspace_id et indexer_used."""
    cache = ApiKeyCache()
    ws_id = uuid4()
    good_key = "good-key"
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        side_effect=[
            {"id": ws_id, "indexer_used": "voyage/voyage-3-lite"},
            {"stored": good_key},
        ]
    )

    ref = McpWorkspaceRef(name="ws", api_key=good_key)
    entry = await _authenticate(ref=ref, config_pool=pool, apikey_cache=cache, api_key_dek=_DEK)
    assert entry.workspace_id == ws_id
    assert entry.indexer_used == "voyage/voyage-3-lite"


@pytest.mark.asyncio
async def test_authenticate_always_hits_db() -> None:
    """NOTE(T6): pas de cache-hit — le DB est toujours consulte."""
    cache = ApiKeyCache()
    ws_id = uuid4()
    good_key = "my-key"
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        side_effect=[
            {"id": ws_id, "indexer_used": "openai/m"},
            {"stored": good_key},
            # deuxieme appel : DB doit etre appele a nouveau (pas de cache)
            {"id": ws_id, "indexer_used": "openai/m"},
            {"stored": good_key},
        ]
    )

    ref = McpWorkspaceRef(name="ws", api_key=good_key)
    await _authenticate(ref=ref, config_pool=pool, apikey_cache=cache, api_key_dek=_DEK)
    await _authenticate(ref=ref, config_pool=pool, apikey_cache=cache, api_key_dek=_DEK)
    # 4 fetchrow calls attendus (2 par appel _authenticate)
    assert pool.fetchrow.call_count == 4


@pytest.mark.asyncio
async def test_load_workspace_context_returns_full_row() -> None:
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "workspace_name": "ws",
            "rag_cnx": "postgresql://...",
            "provider": "openai",
            "model": "text-embedding-3-small",
            "api_key_ref": "openai_embedding_key",
            "base_url": None,
        }
    )
    ctx = await _load_workspace_context(pool, "ws")
    assert ctx["workspace_name"] == "ws"
    assert ctx["provider"] == "openai"
    assert ctx["api_key_ref"] == "openai_embedding_key"


@pytest.mark.asyncio
async def test_load_workspace_context_missing_workspace_raises_runtime() -> None:
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    with pytest.raises(RuntimeError):
        await _load_workspace_context(pool, "ghost")
