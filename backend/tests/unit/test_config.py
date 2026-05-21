from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.config import Settings


def test_settings_minimal_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_123456_padding_padding_padding")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")

    s = Settings()

    assert s.rag_master_key.get_secret_value() == "mk_test_123456_padding_padding_padding"
    assert s.environment == "dev"
    assert s.log_level == "INFO"
    assert s.sync_worker_poll_interval_seconds == 30


def test_settings_missing_master_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.delenv("RAG_MASTER_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings()


def test_settings_master_key_empty_string_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "   ")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")

    with pytest.raises(ValidationError, match="must not be empty"):
        Settings()


def test_sync_default_interval_seconds_defaults_to_300(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_123456_padding_padding_padding")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    s = Settings()
    assert s.sync_default_interval_seconds == 300


def test_sync_default_interval_seconds_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_123456_padding_padding_padding")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("SYNC_DEFAULT_INTERVAL_SECONDS", "60")
    s = Settings()
    assert s.sync_default_interval_seconds == 60


def test_sync_repos_root_defaults_to_var_lib(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_123456_padding_padding_padding")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    s = Settings()
    assert s.sync_repos_root == Path("/var/lib/rag/repos")


def test_sync_repos_root_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_123456_padding_padding_padding")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("SYNC_REPOS_ROOT", "/tmp/test-repos")  # noqa: S108
    s = Settings()
    assert s.sync_repos_root == Path("/tmp/test-repos")  # noqa: S108


def test_settings_ignores_harpocrate_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Depuis M5c, les vars HARPOCRATE_API_TOKEN_*/URL_* sont ignorées au boot
    (extra='ignore' dans model_config). Le boot ne doit pas echouer."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/rag_config")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_123456_padding_padding_padding")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    # Ces variables etaient lues en pre-M5c — elles doivent maintenant etre ignorees.
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_abc")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://vault.example.com")

    s = Settings()
    assert s.rag_master_key.get_secret_value() == "mk_test_123456_padding_padding_padding"
