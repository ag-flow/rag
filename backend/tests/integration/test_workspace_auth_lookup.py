from __future__ import annotations

from hashlib import sha256

import asyncpg
import pytest
from fastapi import FastAPI, HTTPException, Request

from rag.auth.workspace_auth import ApiKeyCache, require_workspace_apikey
from tests.integration._workspace_seed import seed_workspace


def _make_request(app: FastAPI, headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "app": app,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope)


class _StubResolver:
    """Retourne l'api_key en clair pour la ref passée (simple store clé→valeur)."""

    def __init__(self, store: dict[str, str]) -> None:
        self._store = store

    async def resolve_with_retry(self, ref: str) -> str:
        return self._store[ref]


def _make_app(pool: asyncpg.Pool, api_key: str, ws_name: str) -> FastAPI:
    """Construit une app FastAPI minimale câblée pour require_workspace_apikey."""
    app = FastAPI()

    class _Pools:
        config_pool = pool

    ref = f"${{vault://test:{ws_name}_apikey}}"
    store = {ref: api_key}

    app.state.pools = _Pools()
    app.state.apikey_cache = ApiKeyCache()
    app.state.resolver = _StubResolver(store)
    return app


@pytest.mark.asyncio
async def test_valid_apikey_returns_auth_context(migrated: asyncpg.Pool) -> None:
    api_key = "valid-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    async with migrated.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_auth", api_key=api_key)
        # seed un indexer_config minimal (FK requise)
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'ollama', 'mxbai-embed-large', 1024)",
            ws_id,
        )

    app = _make_app(migrated, api_key, "ws_auth")
    req = _make_request(app, {"Authorization": f"Bearer {api_key}"})
    ctx = await require_workspace_apikey("ws_auth", req)
    assert ctx.workspace_id == ws_id


@pytest.mark.asyncio
async def test_unknown_apikey_raises_401(migrated: asyncpg.Pool) -> None:
    async with migrated.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_a", api_key="real-key")
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'ollama', 'mxbai-embed-large', 1024)",
            ws_id,
        )

    app = _make_app(migrated, "real-key", "ws_a")
    req = _make_request(app, {"Authorization": "Bearer fake-key"})
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws_a", req)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_rotated_key_invalidates_old(migrated: asyncpg.Pool) -> None:
    """Après rotation (fingerprint mis à jour en DB + cache invalidé),
    l'ancienne clé est rejetée et la nouvelle est acceptée."""
    old_key = "old-key-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    new_key = "new-key-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

    async with migrated.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_rot", api_key=old_key)
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'ollama', 'mxbai-embed-large', 1024)",
            ws_id,
        )

    app = FastAPI()

    class _Pools:
        config_pool = migrated

    ref = "${vault://test:ws_rot_apikey}"
    store: dict[str, str] = {ref: old_key}

    app.state.pools = _Pools()
    app.state.apikey_cache = ApiKeyCache()
    app.state.resolver = _StubResolver(store)

    # Première auth avec old_key doit passer
    req_old = _make_request(app, {"Authorization": f"Bearer {old_key}"})
    ctx = await require_workspace_apikey("ws_rot", req_old)
    assert ctx.workspace_id == ws_id

    # Simule une rotation : mise à jour fingerprint en DB + ref inchangée
    await migrated.execute(
        "UPDATE workspaces SET api_key_fingerprint = $1 WHERE id = $2",
        sha256(new_key.encode()).hexdigest(),
        ws_id,
    )
    # Mise à jour du store resolver + invalidation cache
    store[ref] = new_key
    app.state.apikey_cache.invalidate(ref)

    # Ancienne clé : fingerprint ne matche plus → 401
    req_old2 = _make_request(app, {"Authorization": f"Bearer {old_key}"})
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws_rot", req_old2)
    assert exc.value.status_code == 401

    # Nouvelle clé : fingerprint matche + resolver retourne new_key → OK
    req_new = _make_request(app, {"Authorization": f"Bearer {new_key}"})
    ctx2 = await require_workspace_apikey("ws_rot", req_new)
    assert ctx2.workspace_id == ws_id
