from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.api.health import build_health_router


def build_test_app() -> FastAPI:
    app = FastAPI()
    app.state.environment = "dev"
    app.state.version = "0.1.0"
    app.state.git_sha = "abc1234"
    app.include_router(build_health_router())
    return app


def test_health_returns_ok() -> None:
    client = TestClient(build_test_app())
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_is_public() -> None:
    client = TestClient(build_test_app())
    r = client.get("/health")
    assert r.status_code == 200


def test_version_endpoint() -> None:
    client = TestClient(build_test_app())
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "0.1.0"
    assert body["git"] == "abc1234"
    assert body["environment"] == "dev"
