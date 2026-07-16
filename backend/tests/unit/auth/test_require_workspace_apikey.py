from __future__ import annotations

# Tests unitaires pour require_workspace_apikey — clés utilisateur hash-only.
# L'écriture (indexation push) exige un grant can_write sur le workspace ;
# la requête SQL porte ce filtre, le mock vérifie le contrat d'appel.
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from rag.auth.workspace_auth import AuthContext, require_workspace_apikey


def _fake_request(headers: dict[str, str], pool):
    return SimpleNamespace(
        headers=headers,
        app=SimpleNamespace(
            state=SimpleNamespace(pools=SimpleNamespace(config_pool=pool))
        ),
    )


@pytest.mark.asyncio
async def test_missing_authorization_header_raises_401() -> None:
    req = _fake_request({}, MagicMock())
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    assert exc.value.detail == "missing_bearer_token"


@pytest.mark.asyncio
async def test_wrong_scheme_raises_401() -> None:
    req = _fake_request({"Authorization": "Basic abc"}, MagicMock())
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_auth_scheme"


@pytest.mark.asyncio
async def test_no_matching_key_or_grant_raises_401_uniform() -> None:
    """Workspace inconnu, clé invalide OU grant can_write absent → 401 uniforme."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    req = _fake_request({"Authorization": "Bearer some-key"}, pool)
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_workspace_apikey"


@pytest.mark.asyncio
async def test_valid_key_with_write_grant_returns_context() -> None:
    ws_id = uuid4()
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value={"id": ws_id, "indexer_used": "openai/text-embedding-3-small"}
    )
    req = _fake_request({"Authorization": "Bearer good-key"}, pool)

    ctx = await require_workspace_apikey("ws", req)  # type: ignore[arg-type]

    assert isinstance(ctx, AuthContext)
    assert ctx.workspace_id == ws_id
    assert ctx.indexer_used == "openai/text-embedding-3-small"
    # Le contrat SQL exige le grant d'écriture sur les clés utilisateur.
    sql = pool.fetchrow.await_args.args[0]
    assert "user_api_keys" in sql
    assert "can_write" in sql


@pytest.mark.asyncio
async def test_write_lookup_never_touches_harpocrate() -> None:
    """Hash-only : un seul fetchrow, aucune résolution de secret."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value={"id": uuid4(), "indexer_used": "voyage/voyage-3"}
    )
    req = _fake_request({"Authorization": "Bearer k"}, pool)
    await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert pool.fetchrow.await_count == 1
