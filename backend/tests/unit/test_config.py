from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

from rag.config import HarpocrateClientConfig, Settings


def test_harpocrate_client_config_is_exported() -> None:
    cfg = HarpocrateClientConfig(url="https://vault.example.com", token="hrpv_1_abc")  # type: ignore[arg-type]
    assert cfg.token.get_secret_value() == "hrpv_1_abc"
    assert str(cfg.url) == "https://vault.example.com/"


def test_settings_minimal_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_123456_padding_padding_padding")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_abc")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://vault.example.com")

    s = Settings()

    assert s.rag_master_key.get_secret_value() == "mk_test_123456_padding_padding_padding"
    assert s.environment == "dev"
    assert s.log_level == "INFO"
    assert s.sync_worker_poll_interval_seconds == 30
    assert "rag" in s.harpocrate_api_keys
    assert s.harpocrate_api_keys["rag"].token.get_secret_value() == "hrpv_1_abc"
    assert str(s.harpocrate_api_keys["rag"].url) == "https://vault.example.com/"


def test_settings_missing_master_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_abc")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://vault.example.com")
    monkeypatch.delenv("RAG_MASTER_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings()


def test_settings_no_harpocrate_keys_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_123456_padding_padding_padding")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    for k in list(os.environ):
        if k.startswith("HARPOCRATE_"):
            monkeypatch.delenv(k, raising=False)

    with pytest.raises(ValidationError, match="No Harpocrate API key configured"):
        Settings()


def test_settings_multiple_harpocrate_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_123456_padding_padding_padding")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_a")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://vault.example.com")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_PROD", "hrpv_1_b")
    monkeypatch.setenv("HARPOCRATE_API_URL_PROD", "https://vault.example.com")

    s = Settings()

    assert set(s.harpocrate_api_keys.keys()) == {"rag", "prod"}


def test_harpocrate_token_missing_url_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_123456_padding_padding_padding")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_ORPHAN", "hrpv_1_x")
    monkeypatch.delenv("HARPOCRATE_API_URL_ORPHAN", raising=False)

    with pytest.raises(ValidationError, match="HARPOCRATE_API_URL_ORPHAN"):
        Settings()


def test_settings_master_key_empty_string_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "   ")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_abc")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://vault.example.com")

    with pytest.raises(ValidationError, match="must not be empty"):
        Settings()


def test_sync_default_interval_seconds_defaults_to_300(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_123456_padding_padding_padding")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_abc")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://vault.example.com")
    s = Settings()
    assert s.sync_default_interval_seconds == 300


def test_sync_default_interval_seconds_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_123456_padding_padding_padding")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_abc")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://vault.example.com")
    monkeypatch.setenv("SYNC_DEFAULT_INTERVAL_SECONDS", "60")
    s = Settings()
    assert s.sync_default_interval_seconds == 60


def test_sync_repos_root_defaults_to_var_lib(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_123456_padding_padding_padding")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_abc")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://vault.example.com")
    s = Settings()
    assert s.sync_repos_root == Path("/var/lib/rag/repos")


def test_sync_repos_root_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_123456_padding_padding_padding")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_abc")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://vault.example.com")
    monkeypatch.setenv("SYNC_REPOS_ROOT", "/tmp/test-repos")  # noqa: S108
    s = Settings()
    assert s.sync_repos_root == Path("/tmp/test-repos")  # noqa: S108
