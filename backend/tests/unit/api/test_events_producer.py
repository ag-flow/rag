"""Router admin du producteur d'events : config GET/PUT (422 event inconnu) + test-connection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.api.admin_events_producer import build_events_producer_router
from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.events.config import EventsProducerConfig
from rag.events.registry import WORKSPACE_CREATED


class _AcquireCM:
    def __init__(self, conn: object) -> None:
        self._conn = conn

    async def __aenter__(self) -> object:
        return self._conn

    async def __aexit__(self, *_exc: object) -> bool:
        return False


def _client(monkeypatch: pytest.MonkeyPatch, cfg: EventsProducerConfig) -> TestClient:
    conn = MagicMock()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AcquireCM(conn))

    from rag.api import admin_events_producer as mod

    monkeypatch.setattr(mod, "get_config", AsyncMock(return_value=cfg))
    monkeypatch.setattr(mod, "put_config", AsyncMock(return_value=cfg))

    app = FastAPI()
    app.state.pools = MagicMock()
    app.state.pools.config_pool = pool
    app.state.resolver = MagicMock()
    app.state.resolver.resolve_with_retry = AsyncMock(return_value="the-secret")
    app.include_router(build_events_producer_router())
    app.dependency_overrides[require_master_key_or_authenticated_admin] = lambda: None
    return TestClient(app)


def _cfg(**over: object) -> EventsProducerConfig:
    base = {
        "enabled": True,
        "workflow_base_url": "https://wf",
        "source_id": "src",
        "secret_ref": "${vault://rag:hmac}",
        "source_uri": "urn:yoops:rag",
        "events": [WORKSPACE_CREATED],
    }
    base.update(over)
    return EventsProducerConfig(**base)  # type: ignore[arg-type]


class TestConfig:
    def test_get_returns_config_and_known_events(self, monkeypatch) -> None:
        resp = _client(monkeypatch, _cfg()).get("/api/admin/events-producer")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert WORKSPACE_CREATED in data["known_events"]

    def test_put_valid(self, monkeypatch) -> None:
        client = _client(monkeypatch, _cfg())
        resp = client.put(
            "/api/admin/events-producer",
            json={
                "enabled": True,
                "workflow_base_url": "https://wf",
                "source_id": "src",
                "secret_ref": "r",
                "source_uri": "urn:yoops:rag",
                "events": [WORKSPACE_CREATED],
            },
        )
        assert resp.status_code == 200

    def test_put_rejects_unknown_event(self, monkeypatch) -> None:
        client = _client(monkeypatch, _cfg())
        resp = client.put(
            "/api/admin/events-producer",
            json={"enabled": True, "events": ["rag.bogus.v1"]},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "unknown_events"


class TestTestConnection:
    def test_posts_signed_test_envelope(self, monkeypatch) -> None:
        # httpx interne du endpoint : on patch AsyncClient pour capturer l'appel.
        captured = {}

        class _FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, content, headers, timeout):  # noqa: ASYNC109
                captured["url"] = url
                captured["sig"] = headers["x-signature"]
                return httpx.Response(202, request=httpx.Request("POST", url))

        monkeypatch.setattr(
            "rag.api.admin_events_producer.httpx.AsyncClient", lambda *a, **k: _FakeClient()
        )
        resp = _client(monkeypatch, _cfg()).post("/api/admin/events-producer/test-connection")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert captured["url"] == "https://wf/events/src"
        assert len(captured["sig"]) == 64

    def test_422_when_not_configured(self, monkeypatch) -> None:
        client = _client(monkeypatch, _cfg(workflow_base_url="", source_id="", secret_ref=""))
        resp = client.post("/api/admin/events-producer/test-connection")
        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "producer_not_configured"
