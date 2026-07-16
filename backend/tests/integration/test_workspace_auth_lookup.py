from __future__ import annotations

import asyncpg
import pytest
from fastapi import FastAPI, HTTPException, Request

from rag.auth.workspace_auth import require_workspace_apikey
from tests.integration._workspace_seed import seed_user_api_key, seed_workspace


def _make_request(app: FastAPI, headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "app": app,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope)


def _make_app(pool: asyncpg.Pool) -> FastAPI:
    app = FastAPI()

    class _Pools:
        config_pool = pool

    app.state.pools = _Pools()
    return app


async def _seed_ws(conn: asyncpg.Connection, name: str):
    ws_id = await seed_workspace(conn, name=name)
    await conn.execute(
        "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
        "VALUES ($1, 'ollama', 'mxbai-embed-large', 1024)",
        ws_id,
    )
    return ws_id


@pytest.mark.asyncio
async def test_key_with_write_grant_returns_auth_context(migrated: asyncpg.Pool) -> None:
    api_key = "valid-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    async with migrated.acquire() as conn:
        ws_id = await _seed_ws(conn, "ws_auth")
        await seed_user_api_key(
            conn, api_key=api_key, grants=[(ws_id, True, True)]
        )

    req = _make_request(_make_app(migrated), {"Authorization": f"Bearer {api_key}"})
    ctx = await require_workspace_apikey("ws_auth", req)
    assert ctx.workspace_id == ws_id


@pytest.mark.asyncio
async def test_unknown_apikey_raises_401(migrated: asyncpg.Pool) -> None:
    async with migrated.acquire() as conn:
        ws_id = await _seed_ws(conn, "ws_a")
        await seed_user_api_key(conn, api_key="real-key", grants=[(ws_id, True, True)])

    req = _make_request(_make_app(migrated), {"Authorization": "Bearer fake-key"})
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws_a", req)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_read_only_grant_rejected_for_write(migrated: asyncpg.Pool) -> None:
    """Une clé can_read sans can_write ne peut pas pousser d'indexation."""
    api_key = "read-only-key-cccccccccccccccccccccccc"
    async with migrated.acquire() as conn:
        ws_id = await _seed_ws(conn, "ws_ro")
        await seed_user_api_key(
            conn, api_key=api_key, grants=[(ws_id, True, False)]
        )

    req = _make_request(_make_app(migrated), {"Authorization": f"Bearer {api_key}"})
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws_ro", req)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_grant_on_other_workspace_rejected(migrated: asyncpg.Pool) -> None:
    """Le grant est par workspace : une clé valide ailleurs est refusée ici."""
    api_key = "other-ws-key-dddddddddddddddddddddddd"
    async with migrated.acquire() as conn:
        ws_granted = await _seed_ws(conn, "ws_granted")
        await _seed_ws(conn, "ws_target")
        await seed_user_api_key(
            conn, api_key=api_key, grants=[(ws_granted, True, True)]
        )

    req = _make_request(_make_app(migrated), {"Authorization": f"Bearer {api_key}"})
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws_target", req)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_revoked_key_rejected(migrated: asyncpg.Pool) -> None:
    api_key = "revoked-key-eeeeeeeeeeeeeeeeeeeeeeeeee"
    async with migrated.acquire() as conn:
        ws_id = await _seed_ws(conn, "ws_rev")
        key_id = await seed_user_api_key(
            conn, api_key=api_key, grants=[(ws_id, True, True)]
        )
        await conn.execute(
            "UPDATE user_api_keys SET revoked_at = now() WHERE id = $1", key_id
        )

    req = _make_request(_make_app(migrated), {"Authorization": f"Bearer {api_key}"})
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws_rev", req)
    assert exc.value.status_code == 401
