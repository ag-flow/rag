"""Connexion locale pilotée par le store admin.env (RAG_LOCAL_AUTH_DISABLED).

Quand la connexion locale est désactivée :
- `/api/auth/methods` renvoie `local_auth_enabled=false` +
  `local_auth_disabled_by_config=true` ;
- `POST /auth/local/login` est refusé avec 403 `local_auth_disabled`
  (l'enforcement ne repose pas sur le seul masquage UI).

Le toggle et le client secret OIDC se pilotent via `/api/admin/*` et sont
persistés dans admin.env (relu à chaud).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.admin_env import AdminEnvStore
from rag.api.admin_auth_config import build_admin_auth_config_router
from rag.api.auth import build_auth_router
from rag.api.auth_methods import build_auth_methods_router
from rag.api.errors import register_error_handlers
from rag.auth.bearer import require_master_key_or_authenticated_admin


def _app(tmp_path: Path, *, user_count: int = 1) -> tuple[FastAPI, AdminEnvStore]:
    store = AdminEnvStore(tmp_path / "admin.env")
    app = FastAPI()
    app.state.admin_env = store
    app.state.local_auth = MagicMock()
    app.state.local_auth.user_count = AsyncMock(return_value=user_count)
    app.state.oidc = MagicMock()
    app.state.oidc.get_config = AsyncMock(return_value=None)
    app.include_router(build_auth_router())
    app.include_router(build_auth_methods_router())
    app.include_router(build_admin_auth_config_router(), prefix="/api/admin")
    app.dependency_overrides[require_master_key_or_authenticated_admin] = lambda: None
    register_error_handlers(app)
    return app, store


class TestAuthMethodsFlag:
    def test_methods_default_enabled(self, tmp_path: Path) -> None:
        app, _ = _app(tmp_path)
        body = TestClient(app).get("/api/auth/methods").json()
        assert body["local_auth_enabled"] is True
        assert body["local_auth_disabled_by_config"] is False

    def test_methods_reports_disabled(self, tmp_path: Path) -> None:
        app, store = _app(tmp_path)
        store.set_local_auth_disabled(True)
        body = TestClient(app).get("/api/auth/methods").json()
        assert body["local_auth_enabled"] is False
        assert body["local_auth_disabled_by_config"] is True


class TestLocalLoginEnforcement:
    def test_login_refused_403_when_disabled(self, tmp_path: Path) -> None:
        app, store = _app(tmp_path)
        store.set_local_auth_disabled(True)
        resp = TestClient(app).post(
            "/auth/local/login",
            json={"username": "admin", "password": "whatever-password"},
        )
        assert resp.status_code == 403
        assert resp.json()["error"] == "local_auth_disabled"


class TestAdminEndpoints:
    def test_toggle_local_login_via_ihm(self, tmp_path: Path) -> None:
        app, store = _app(tmp_path)
        client = TestClient(app)

        # État par défaut : activé.
        assert client.get("/api/admin/auth/local-login").json() == {"enabled": True}

        # Désactivation via l'IHM → persistée + effet immédiat sur /methods.
        r = client.put("/api/admin/auth/local-login", json={"enabled": False})
        assert r.json() == {"enabled": False}
        assert store.is_local_auth_disabled() is True
        assert client.get("/api/auth/methods").json()["local_auth_enabled"] is False

        # Réactivation.
        client.put("/api/admin/auth/local-login", json={"enabled": True})
        assert store.is_local_auth_disabled() is False

    def test_set_client_secret_via_ihm(self, tmp_path: Path) -> None:
        app, store = _app(tmp_path)
        client = TestClient(app)

        assert client.get("/api/admin/oidc/client-secret").json() == {"configured": False}

        r = client.put("/api/admin/oidc/client-secret", json={"value": "hrpv_secret"})
        assert r.json() == {"configured": True}
        assert store.get_oidc_client_secret() == "hrpv_secret"
        assert client.get("/api/admin/oidc/client-secret").json() == {"configured": True}

    def test_set_client_secret_rejects_newline(self, tmp_path: Path) -> None:
        app, _ = _app(tmp_path)
        r = TestClient(app).put(
            "/api/admin/oidc/client-secret", json={"value": "bad\nvalue"}
        )
        assert r.status_code == 422
