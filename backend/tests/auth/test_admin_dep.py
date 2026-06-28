from __future__ import annotations

import time

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from rag.api.errors import register_error_handlers
from rag.auth.bearer import _LOCAL_SESSION_KEY, require_master_key_or_authenticated_admin
from unittest.mock import AsyncMock, MagicMock

from rag.services.local_auth import LocalAuthService


class _StubOidcService:
    """No OIDC config → require_oidc_role raises OidcNotConfigured (mapped to 503)
    OR OidcSessionMissing si cookie absent. Dans tous les cas, le chemin de
    fallback échoue avec 4xx/5xx quand pas de Bearer ni de session locale.
    """

    async def get_config(self):
        return None


@pytest.fixture
def app_with_dep() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="a" * 32)
    app.state.master_key = "test-master-key-123"
    stub_pool = MagicMock()
    app.state.local_auth = LocalAuthService(pool=stub_pool, ttl_seconds=3600)
    app.state.oidc = _StubOidcService()
    register_error_handlers(app)

    @app.get("/protected")
    async def protected(_: None = Depends(require_master_key_or_authenticated_admin)) -> dict:
        return {"ok": True}

    @app.post("/_setup_local_session")
    async def setup(request: Request) -> dict:
        request.session[_LOCAL_SESSION_KEY] = {
            "username": "admin",
            "expires_at": int(time.time()) + 3600,
        }
        return {"ok": True}

    @app.post("/_setup_expired_local_session")
    async def setup_expired(request: Request) -> dict:
        request.session[_LOCAL_SESSION_KEY] = {
            "username": "admin",
            "expires_at": int(time.time()) - 1,
        }
        return {"ok": True}

    return app


def test_bearer_master_key_valid_returns_200(app_with_dep: FastAPI) -> None:
    client = TestClient(app_with_dep)
    resp = client.get(
        "/protected",
        headers={"Authorization": "Bearer test-master-key-123"},
    )
    assert resp.status_code == 200


def test_bearer_master_key_invalid_returns_401(app_with_dep: FastAPI) -> None:
    client = TestClient(app_with_dep)
    resp = client.get("/protected", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_local_session_valid_returns_200(app_with_dep: FastAPI) -> None:
    client = TestClient(app_with_dep)
    client.post("/_setup_local_session")
    resp = client.get("/protected")
    assert resp.status_code == 200


def test_local_session_expired_returns_401(app_with_dep: FastAPI) -> None:
    client = TestClient(app_with_dep)
    client.post("/_setup_expired_local_session")
    resp = client.get("/protected")
    assert resp.status_code == 401
    assert resp.json()["error"] == "local_session_expired"


def test_no_auth_falls_through_to_oidc_and_returns_401(app_with_dep: FastAPI) -> None:
    """No Bearer, no local session → fallback OIDC.

    require_oidc_role vérifie d'abord le cookie _oidc_session : absent →
    OidcSessionMissing (401) de façon déterministe, avant même d'appeler
    get_config(). L'assertion est donc exactement 401, non ambiguë.
    """
    client = TestClient(app_with_dep)
    resp = client.get("/protected")
    assert resp.status_code == 401
