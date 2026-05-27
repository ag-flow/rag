from __future__ import annotations

# Tests unitaires pour require_workspace_apikey (T6 -- cache + Harpocrate).
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from rag.auth.workspace_auth import (
    ApiKeyCache,
    AuthContext,
    require_workspace_apikey,
)


def _fake_request(headers: dict[str, str], pool, cache: ApiKeyCache, resolver=None):
    if resolver is None:
        resolver = MagicMock()
    return SimpleNamespace(
        headers=headers,
        app=SimpleNamespace(
            state=SimpleNamespace(
                apikey_cache=cache,
                pools=SimpleNamespace(config_pool=pool),
                resolver=resolver,
            )
        ),
    )


@pytest.mark.asyncio
async def test_missing_authorization_header_raises_401() -> None:
    cache = ApiKeyCache()
    pool = MagicMock()
    req = _fake_request({}, pool, cache)
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    assert exc.value.detail == "missing_bearer_token"


@pytest.mark.asyncio
async def test_wrong_scheme_raises_401() -> None:
    cache = ApiKeyCache()
    pool = MagicMock()
    req = _fake_request({"Authorization": "Basic abc"}, pool, cache)
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_auth_scheme"


@pytest.mark.asyncio
async def test_workspace_not_found_raises_401() -> None:
    """Workspace inconnu (fetchrow None) -> 401 uniforme."""
    cache = ApiKeyCache()
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    req = _fake_request({"Authorization": "Bearer some-key"}, pool, cache)
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ghost", req)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_workspace_apikey"


@pytest.mark.asyncio
async def test_invalid_key_raises_401() -> None:
    """compare_digest echoue (resolver retourne cle differente) -> 401."""
    ref = "${vault://rag:wsapi_ws}"
    cache = ApiKeyCache()
    ws_id = uuid4()
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "id": ws_id,
            "api_key_ref": ref,
            "indexer_used": "openai/text-embedding-3-small",
        }
    )
    resolver = MagicMock()
    resolver.resolve_with_retry = AsyncMock(return_value="the-real-stored-key")
    req = _fake_request({"Authorization": "Bearer bad-key"}, pool, cache, resolver)
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_workspace_apikey"


@pytest.mark.asyncio
async def test_valid_key_returns_auth_context() -> None:
    """Cle valide -> AuthContext retourne avec workspace_id et indexer_used."""
    ref = "${vault://rag:wsapi_ws}"
    cache = ApiKeyCache()
    ws_id = uuid4()
    good_key = "good-key"
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "id": ws_id,
            "api_key_ref": ref,
            "indexer_used": "voyage/voyage-3-lite",
        }
    )
    resolver = MagicMock()
    resolver.resolve_with_retry = AsyncMock(return_value=good_key)
    req = _fake_request({"Authorization": f"Bearer {good_key}"}, pool, cache, resolver)
    ctx = await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert isinstance(ctx, AuthContext)
    assert ctx.workspace_id == ws_id
    assert ctx.indexer_used == "voyage/voyage-3-lite"


@pytest.mark.asyncio
async def test_harpocrate_unreachable_raises_503() -> None:
    """Si Harpocrate est inaccessible sur cache miss -> 503 harpocrate_unreachable."""
    from rag.api.errors import HarpocrateUnreachableForApikey, VaultUnreachable

    ref = "${vault://rag:wsapi_ws}"
    cache = ApiKeyCache()
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "id": uuid4(),
            "api_key_ref": ref,
            "indexer_used": "ollama/mxbai",
        }
    )
    resolver = MagicMock()
    resolver.resolve_with_retry = AsyncMock(side_effect=VaultUnreachable("down"))
    req = _fake_request({"Authorization": "Bearer some-key"}, pool, cache, resolver)
    with pytest.raises(HarpocrateUnreachableForApikey):
        await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
