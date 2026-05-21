from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from rag.api.errors import register_error_handlers
from rag.auth.workspace_auth import ApiKeyCache, require_workspace_apikey


@pytest.fixture
def app_with_auth() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="a" * 32)
    register_error_handlers(app)

    app.state.apikey_cache = ApiKeyCache()
    app.state.pools = MagicMock()
    app.state.pools.config_pool = MagicMock()
    app.state.resolver = MagicMock()

    @app.get("/ws/{name}/check")
    async def check(name: str, request: Request):
        ctx = await require_workspace_apikey(name, request)
        return {"workspace_id": str(ctx.workspace_id), "indexer": ctx.indexer_used}

    return app


def test_require_apikey_cache_hit_does_not_call_harpocrate(app_with_auth: FastAPI) -> None:
    ref = "${vault://rag:wsapi_test1}"
    api_key = "secret-clear-value"
    app_with_auth.state.apikey_cache.put(ref, api_key)

    workspace_id = uuid4()
    app_with_auth.state.pools.config_pool.fetchrow = AsyncMock(
        return_value={
            "id": workspace_id,
            "api_key_ref": ref,
            "indexer_used": "ollama/mxbai",
        }
    )
    app_with_auth.state.resolver.resolve_with_retry = AsyncMock(
        side_effect=Exception("resolver should not be called"),
    )

    client = TestClient(app_with_auth)
    resp = client.get("/ws/test1/check", headers={"Authorization": f"Bearer {api_key}"})
    assert resp.status_code == 200
    app_with_auth.state.resolver.resolve_with_retry.assert_not_called()


def test_require_apikey_cache_miss_resolves_from_harpocrate_and_caches(
    app_with_auth: FastAPI,
) -> None:
    ref = "${vault://rag:wsapi_test1}"
    api_key = "fresh-from-harpocrate"
    workspace_id = uuid4()
    app_with_auth.state.pools.config_pool.fetchrow = AsyncMock(
        return_value={
            "id": workspace_id,
            "api_key_ref": ref,
            "indexer_used": "ollama/mxbai",
        }
    )
    app_with_auth.state.resolver.resolve_with_retry = AsyncMock(return_value=api_key)

    client = TestClient(app_with_auth)
    resp = client.get("/ws/test1/check", headers={"Authorization": f"Bearer {api_key}"})
    assert resp.status_code == 200
    app_with_auth.state.resolver.resolve_with_retry.assert_awaited_once_with(ref)
    assert app_with_auth.state.apikey_cache.get(ref) == api_key


def test_require_apikey_harpocrate_unreachable_returns_503(app_with_auth: FastAPI) -> None:
    from rag.api.errors import VaultUnreachable

    ref = "${vault://rag:wsapi_test1}"
    api_key = "some-key"
    app_with_auth.state.pools.config_pool.fetchrow = AsyncMock(
        return_value={
            "id": uuid4(),
            "api_key_ref": ref,
            "indexer_used": "ollama/mxbai",
        }
    )
    app_with_auth.state.resolver.resolve_with_retry = AsyncMock(
        side_effect=VaultUnreachable("test")
    )

    client = TestClient(app_with_auth)
    resp = client.get("/ws/test1/check", headers={"Authorization": f"Bearer {api_key}"})
    assert resp.status_code == 503
    assert resp.json()["error"] == "harpocrate_unreachable"


def test_require_apikey_wrong_key_returns_401(app_with_auth: FastAPI) -> None:
    """Lookup fingerprint(wrong_bearer) ne trouve aucune row -> 401 uniform."""
    app_with_auth.state.pools.config_pool.fetchrow = AsyncMock(return_value=None)

    client = TestClient(app_with_auth)
    resp = client.get("/ws/test1/check", headers={"Authorization": "Bearer wrong-key"})
    assert resp.status_code == 401


def test_require_apikey_unknown_workspace_returns_401(app_with_auth: FastAPI) -> None:
    app_with_auth.state.pools.config_pool.fetchrow = AsyncMock(return_value=None)
    client = TestClient(app_with_auth)
    resp = client.get("/ws/ghost/check", headers={"Authorization": "Bearer anything"})
    assert resp.status_code == 401
