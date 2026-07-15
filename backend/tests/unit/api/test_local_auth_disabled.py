"""Flag `RAG_LOCAL_AUTH_DISABLED` — désactivation de la connexion locale.

Source de vérité dans le .env (Settings). Quand le flag est actif :
- `/api/auth/methods` renvoie `local_auth_enabled=false` +
  `local_auth_disabled_by_config=true` (la page login masque le formulaire
  local et n'affiche que le SSO) ;
- `POST /auth/local/login` est refusé avec 403 `local_auth_disabled`
  (l'enforcement ne repose pas seulement sur le masquage UI).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.api.auth import build_auth_router
from rag.api.auth_methods import build_auth_methods_router
from rag.api.errors import register_error_handlers
from rag.config import Settings


def _base_env(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@localhost:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "x" * 64)
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")


def _client(monkeypatch, *, disabled: bool, user_count: int = 1) -> TestClient:
    _base_env(monkeypatch)
    monkeypatch.setenv("RAG_LOCAL_AUTH_DISABLED", "true" if disabled else "false")

    app = FastAPI()
    app.state.settings = Settings()  # type: ignore[call-arg]
    app.state.local_auth = MagicMock()
    app.state.local_auth.user_count = AsyncMock(return_value=user_count)
    app.state.oidc = MagicMock()
    app.state.oidc.get_config = AsyncMock(return_value=None)
    app.include_router(build_auth_router())
    app.include_router(build_auth_methods_router())
    register_error_handlers(app)
    return TestClient(app)


class TestAuthMethodsFlag:
    def test_methods_reports_disabled_by_config(self, monkeypatch) -> None:
        client = _client(monkeypatch, disabled=True)
        body = client.get("/api/auth/methods").json()
        assert body["local_auth_enabled"] is False
        assert body["local_auth_disabled_by_config"] is True
        assert body["needs_setup"] is False

    def test_methods_enabled_when_flag_off(self, monkeypatch) -> None:
        client = _client(monkeypatch, disabled=False)
        body = client.get("/api/auth/methods").json()
        assert body["local_auth_enabled"] is True
        assert body["local_auth_disabled_by_config"] is False


class TestLocalLoginEnforcement:
    def test_login_refused_403_when_disabled(self, monkeypatch) -> None:
        client = _client(monkeypatch, disabled=True)
        resp = client.post(
            "/auth/local/login",
            json={"username": "admin", "password": "whatever-password"},
        )
        assert resp.status_code == 403
        assert resp.json()["error"] == "local_auth_disabled"
