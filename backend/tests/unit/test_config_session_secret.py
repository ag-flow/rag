from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from rag.config import Settings

_BASE_ENV = {
    "DATABASE_URL": "postgresql://u:p@localhost:5432/rag_config",
    "RAG_POSTGRES_ADMIN_URL": "postgresql://u:p@localhost:5432/postgres",
    "RAG_MASTER_KEY": "x" * 40,  # 40 chars > 32 min
    "RAG_PUBLIC_URL": "http://localhost:8000",
}


def test_session_secret_uses_explicit_value_when_provided() -> None:
    env = {**_BASE_ENV, "RAG_SESSION_SECRET": "y" * 50}
    with patch.dict(os.environ, env, clear=True):
        s = Settings()  # type: ignore[call-arg]
        assert s.rag_session_secret.get_secret_value() == "y" * 50


def test_session_secret_falls_back_to_master_key_when_absent() -> None:
    env = {k: v for k, v in _BASE_ENV.items() if k != "RAG_SESSION_SECRET"}
    with patch.dict(os.environ, env, clear=True):
        s = Settings()  # type: ignore[call-arg]
        assert s.rag_session_secret.get_secret_value() == "x" * 40


def test_session_secret_rejected_when_too_short() -> None:
    env = {**_BASE_ENV, "RAG_SESSION_SECRET": "tooshort"}
    with patch.dict(os.environ, env, clear=True), pytest.raises(ValueError, match="32"):
        Settings()  # type: ignore[call-arg]


def test_master_key_too_short_blocks_fallback() -> None:
    """Si pas de RAG_SESSION_SECRET et que RAG_MASTER_KEY est aussi < 32,
    le fallback échoue avec un message clair."""
    env = {
        **{k: v for k, v in _BASE_ENV.items() if k != "RAG_SESSION_SECRET"},
        "RAG_MASTER_KEY": "shortkey",
    }
    with patch.dict(os.environ, env, clear=True), pytest.raises(ValueError, match="32"):
        Settings()  # type: ignore[call-arg]
