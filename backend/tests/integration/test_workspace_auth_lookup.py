from __future__ import annotations

from hashlib import sha256

import asyncpg
import pytest
from fastapi import FastAPI, HTTPException, Request
from starlette.datastructures import Headers

from rag.auth.workspace_auth import ApiKeyCache, require_workspace_apikey
from tests.integration._workspace_seed import seed_workspace


def _make_request(app: FastAPI, headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "app": app,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_valid_apikey_returns_auth_context(migrated: asyncpg.Pool) -> None:
    api_key = "valid-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    dek = "x" * 32
    async with migrated.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_auth", api_key=api_key, dek=dek)
        # seed un indexer_config minimal (FK requise)
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'ollama', 'mxbai-embed-large', 1024)",
            ws_id,
        )

    app = FastAPI()

    class _Pools:
        config_pool = migrated

    class _Settings:
        api_key_dek = dek

    app.state.pools = _Pools()
    app.state.apikey_cache = ApiKeyCache()
    app.state.settings = _Settings()

    req = _make_request(app, {"Authorization": f"Bearer {api_key}"})
    ctx = await require_workspace_apikey("ws_auth", req)
    assert ctx.workspace_id == ws_id


@pytest.mark.asyncio
async def test_unknown_apikey_raises_401(migrated: asyncpg.Pool) -> None:
    dek = "x" * 32
    async with migrated.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_a", api_key="real-key", dek=dek)
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'ollama', 'mxbai-embed-large', 1024)",
            ws_id,
        )

    app = FastAPI()

    class _Pools:
        config_pool = migrated

    class _Settings:
        api_key_dek = dek

    app.state.pools = _Pools()
    app.state.apikey_cache = ApiKeyCache()
    app.state.settings = _Settings()

    req = _make_request(app, {"Authorization": "Bearer fake-key"})
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws_a", req)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_rotated_key_invalidates_old(migrated: asyncpg.Pool) -> None:
    """L'ancienne clé ne valide plus après une rotation manuelle (UPDATE direct)."""
    old_key = "old-key-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    new_key = "new-key-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    dek = "x" * 32
    async with migrated.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_rot", api_key=old_key, dek=dek)
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'ollama', 'mxbai-embed-large', 1024)",
            ws_id,
        )
        # rotation manuelle (simule rotate_apikey)
        await conn.execute(
            "UPDATE workspaces SET "
            "api_key_encrypted = pgp_sym_encrypt($1::text, $2::text)::bytea, "
            "api_key_fingerprint = $3 WHERE id = $4",
            new_key, dek, sha256(new_key.encode()).hexdigest(), ws_id,
        )

    app = FastAPI()

    class _Pools:
        config_pool = migrated

    class _Settings:
        api_key_dek = dek

    app.state.pools = _Pools()
    app.state.apikey_cache = ApiKeyCache()
    app.state.settings = _Settings()

    req_old = _make_request(app, {"Authorization": f"Bearer {old_key}"})
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws_rot", req_old)
    assert exc.value.status_code == 401

    req_new = _make_request(app, {"Authorization": f"Bearer {new_key}"})
    ctx = await require_workspace_apikey("ws_rot", req_new)
    assert ctx.workspace_id == ws_id
