from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.config import Settings


def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Variables minimales requises par Settings pour qu'il soit instanciable."""
    monkeypatch.setenv("RAG_MASTER_KEY", "master-key-32-chars-min-xxxxxxxxxx")
    monkeypatch.setenv("DATABASE_URL", "postgresql://r:r@h/db")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://r:r@h/postgres")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")


def test_api_key_dek_absent_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.delenv("RAG_API_KEY_DEK", raising=False)
    s = Settings()
    assert s.api_key_dek is None


def test_api_key_dek_empty_string_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("RAG_API_KEY_DEK", "")
    s = Settings()
    assert s.api_key_dek is None


def test_api_key_dek_too_short_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("RAG_API_KEY_DEK", "x" * 31)
    with pytest.raises(ValidationError, match="32 caractères"):
        Settings()


def test_api_key_dek_exactly_32_chars_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("RAG_API_KEY_DEK", "x" * 32)
    s = Settings()
    assert s.api_key_dek == "x" * 32
