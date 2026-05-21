from __future__ import annotations

# Tests unitaires pour require_workspace_apikey (T1 -- lookup DB direct).
# NOTE(T6): le cache n'est pas utilise dans require_workspace_apikey pour
# l'instant -- tous les appels passent par le DB. Tests cache-hit/miss en T6.
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

_DEK = "x" * 32


def _fake_request(headers: dict[str, str], pool, cache: ApiKeyCache):
    return SimpleNamespace(
        headers=headers,
        app=SimpleNamespace(
            state=SimpleNamespace(
                apikey_cache=cache,
                pools=SimpleNamespace(config_pool=pool),
                settings=SimpleNamespace(api_key_dek=_DEK),
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
    """compare_digest echoue (stored != presente) -> 401."""
    cache = ApiKeyCache()
    ws_id = uuid4()
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "id": ws_id,
            "stored": "the-real-stored-key",
            "indexer_used": "openai/text-embedding-3-small",
        }
    )
    req = _fake_request({"Authorization": "Bearer bad-key"}, pool, cache)
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_workspace_apikey"


@pytest.mark.asyncio
async def test_valid_key_returns_auth_context() -> None:
    """Cle valide -> AuthContext retourne avec workspace_id et indexer_used."""
    cache = ApiKeyCache()
    ws_id = uuid4()
    good_key = "good-key"
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "id": ws_id,
            "stored": good_key,
            "indexer_used": "voyage/voyage-3-lite",
        }
    )
    req = _fake_request({"Authorization": f"Bearer {good_key}"}, pool, cache)
    ctx = await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert isinstance(ctx, AuthContext)
    assert ctx.workspace_id == ws_id
    assert ctx.indexer_used == "voyage/voyage-3-lite"


@pytest.mark.asyncio
async def test_dek_absent_raises_503() -> None:
    """Si api_key_dek est None en settings -> 503 avant tout acces DB."""
    cache = ApiKeyCache()
    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=AssertionError("pool must not be called when DEK absent"))

    req = SimpleNamespace(
        headers={"Authorization": "Bearer some-key"},
        app=SimpleNamespace(
            state=SimpleNamespace(
                apikey_cache=cache,
                pools=SimpleNamespace(config_pool=pool),
                settings=SimpleNamespace(api_key_dek=None),
            )
        ),
    )
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert exc.value.status_code == 503
    assert exc.value.detail == "api_key_dek_unavailable"
