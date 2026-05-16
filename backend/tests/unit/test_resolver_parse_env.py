from __future__ import annotations

import pytest

from rag.secrets.resolver import (
    EnvVarMissing,
    ParsedRef,
    SecretResolver,
    UnknownAction,
    parse_ref,
)


def test_parse_literal_returns_none() -> None:
    assert parse_ref("sk-literal-value") is None
    assert parse_ref("") is None
    assert parse_ref("plain string") is None


def test_parse_env_ref() -> None:
    ref = parse_ref("${env://OPENAI_API_KEY}")
    assert ref == ParsedRef(action="env", api_key_id=None, path="OPENAI_API_KEY")


def test_parse_vault_ref_root() -> None:
    ref = parse_ref("${vault://api1:anthropic_api_key}")
    assert ref == ParsedRef(action="vault", api_key_id="api1", path="anthropic_api_key")


def test_parse_vault_ref_nested() -> None:
    ref = parse_ref("${vault://prod:shared/databases/postgres_url}")
    assert ref == ParsedRef(action="vault", api_key_id="prod", path="shared/databases/postgres_url")


def test_parse_vault_with_email_segment() -> None:
    ref = parse_ref("${vault://api1:alice@example.com/github_token}")
    assert ref == ParsedRef(
        action="vault", api_key_id="api1", path="alice@example.com/github_token"
    )


def test_parse_unknown_action_raises() -> None:
    with pytest.raises(UnknownAction):
        parse_ref("${file:///etc/passwd}")


async def test_resolver_returns_literal_unchanged() -> None:
    r = SecretResolver(harpocrate_clients={})
    assert await r.resolve("plain-token") == "plain-token"


async def test_resolver_resolves_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_KEY", "value-from-env")
    r = SecretResolver(harpocrate_clients={})
    assert await r.resolve("${env://MY_KEY}") == "value-from-env"


async def test_resolver_env_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ABSENT", raising=False)
    r = SecretResolver(harpocrate_clients={})
    with pytest.raises(EnvVarMissing, match="ABSENT"):
        await r.resolve("${env://ABSENT}")
