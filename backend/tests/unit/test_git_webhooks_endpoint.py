from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from rag.api.git_webhooks import build_git_webhooks_router


def _make_app(source_row: dict | None) -> FastAPI:
    app = FastAPI()
    app.state.pools = MagicMock()

    conn_mock = AsyncMock()
    conn_mock.fetchrow = AsyncMock(return_value=source_row)
    conn_mock.execute = AsyncMock()

    pool_mock = MagicMock(spec=asyncpg.Pool)
    pool_mock.acquire.return_value.__aenter__ = AsyncMock(return_value=conn_mock)
    pool_mock.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    app.state.pools.config_pool = pool_mock

    resolver_mock = MagicMock()
    resolver_mock.resolve_with_retry = AsyncMock(return_value="mysecret")
    app.state.resolver = resolver_mock

    app.include_router(build_git_webhooks_router())
    return app


PAYLOAD = json.dumps({"ref": "refs/heads/main"}).encode()
SECRET = "mysecret"


def _github_sig(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_webhook_404_when_source_not_found() -> None:
    app = _make_app(source_row=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/webhooks/git/myws/myrepo",
            content=PAYLOAD,
            headers={"x-hub-signature-256": _github_sig(PAYLOAD, SECRET)},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_webhook_404_when_not_enabled() -> None:
    source = {
        "id": "uuid-1",
        "webhook_enabled": False,
        "config": json.dumps({"git_provider": "github", "branch": "main",
                              "webhook_secret_ref": "${vault://v:/p}"}),
    }
    app = _make_app(source_row=source)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/webhooks/git/myws/myrepo",
            content=PAYLOAD,
            headers={"x-hub-signature-256": _github_sig(PAYLOAD, SECRET)},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_webhook_401_invalid_signature() -> None:
    source = {
        "id": "uuid-1",
        "webhook_enabled": True,
        "config": json.dumps({"git_provider": "github", "branch": "main",
                              "webhook_secret_ref": "${vault://v:/p}"}),
    }
    app = _make_app(source_row=source)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/webhooks/git/myws/myrepo",
            content=PAYLOAD,
            headers={"x-hub-signature-256": "sha256=bad"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_200_wrong_branch_silent() -> None:
    source = {
        "id": "uuid-1",
        "webhook_enabled": True,
        "config": json.dumps({"git_provider": "github", "branch": "main",
                              "webhook_secret_ref": "${vault://v:/p}"}),
    }
    app = _make_app(source_row=source)
    payload = json.dumps({"ref": "refs/heads/other"}).encode()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/webhooks/git/myws/myrepo",
            content=payload,
            headers={"x-hub-signature-256": _github_sig(payload, SECRET)},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
