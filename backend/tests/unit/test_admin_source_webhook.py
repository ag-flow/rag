from __future__ import annotations

from rag.schemas.admin import WebhookEnableResponse


def test_webhook_enable_response_fields() -> None:
    r = WebhookEnableResponse(
        source_name="my-repo",
        webhook_url="https://rag.example.com/api/webhooks/git/ws1/my-repo",
        secret="abc123",
    )
    assert r.source_name == "my-repo"
    assert "my-repo" in r.webhook_url
    assert r.secret == "abc123"
