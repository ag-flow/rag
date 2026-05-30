from __future__ import annotations

import pytest

from rag.services.source_webhooks import (
    WebhookAlreadyEnabledError,
    WebhookNotEnabledError,
    _build_harpo_path,
    _build_vault_ref,
)


def test_build_harpo_path() -> None:
    assert _build_harpo_path("myws", "my-repo") == "sources/myws/my-repo/webhook_secret"


def test_build_vault_ref() -> None:
    ref = _build_vault_ref("vault1", "myws", "my-repo")
    assert ref == "${vault://vault1:/sources/myws/my-repo/webhook_secret}"


def test_webhook_already_enabled_is_exception() -> None:
    exc = WebhookAlreadyEnabledError("myws", "repo")
    assert "myws" in str(exc)


def test_webhook_not_enabled_is_exception() -> None:
    exc = WebhookNotEnabledError("myws", "repo")
    assert "repo" in str(exc)
