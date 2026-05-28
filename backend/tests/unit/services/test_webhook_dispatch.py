from __future__ import annotations

import hashlib
import hmac
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag.services.webhook_dispatch import (
    _build_payload,
    _sign_payload,
    dispatch_webhooks,
)


def test_sign_payload_sha256() -> None:
    secret = "my-secret"
    payload = b'{"event":"test"}'
    sig = _sign_payload(secret, payload)
    assert sig is not None
    assert sig.startswith("sha256=")
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert sig == f"sha256={expected}"


def test_sign_payload_none_secret_returns_none() -> None:
    assert _sign_payload(None, b"data") is None


def test_build_payload_push() -> None:
    payload = _build_payload(
        event="indexation.completed",
        workspace="ws1",
        triggered_by="push",
        job_id="uuid-1",
        status="done",
        files_changed=1,
        files_skipped=0,
        duration_ms=340,
        finished_at="2026-05-28T10:00:00Z",
        error_message=None,
    )
    assert payload["event"] == "indexation.completed"
    assert payload["triggered_by"] == "push"
    assert payload["status"] == "done"
    assert "git_commit" not in payload


@pytest.mark.asyncio
async def test_dispatch_webhooks_calls_all_enabled() -> None:
    pool = MagicMock()
    calls_received: list[str] = []

    async def fake_http_post(url: str, **kw: Any) -> MagicMock:
        calls_received.append(url)
        r = MagicMock()
        r.status_code = 200
        return r

    with patch(
        "rag.services.webhook_dispatch.fetch_all",
        side_effect=[
            [
                {"id": "wh-1", "url": "https://a.com/hook"},
                {"id": "wh-2", "url": "https://b.com/hook"},
            ],
            [],  # headers wh-1
            [],  # headers wh-2
        ],
    ), patch(
        "rag.services.webhook_dispatch._http_post",
        new=AsyncMock(side_effect=fake_http_post),
    ), patch(
        "rag.services.webhook_dispatch._insert_call",
        new=AsyncMock(),
    ):
        await dispatch_webhooks(
            config_pool=pool,
            workspace_id="ws-id",
            workspace_name="ws1",
            job_id="job-1",
            correlation_id="corr-1",
            triggered_by="push",
            status="done",
            files_changed=1,
            files_skipped=0,
            duration_ms=100,
            finished_at="2026-05-28T10:00:00Z",
            error_message=None,
            webhook_secret=None,
            resolver=None,
        )

    assert len(calls_received) == 2
    assert "https://a.com/hook" in calls_received
    assert "https://b.com/hook" in calls_received
