from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.config import Settings


def _base_env(**overrides):
    # NB: le plan d'origine omettait RAG_POSTGRES_ADMIN_URL et RAG_PUBLIC_URL
    # qui sont des champs requis de Settings (pas de valeur par défaut).
    # On les ajoute ici pour que Settings() puisse s'instancier sans dépendre
    # d'un .env local pollué.
    base = {
        "RAG_MASTER_KEY": "x" * 64,
        "DATABASE_URL": "postgresql://u:p@localhost:5432/db",
        "RAG_POSTGRES_ADMIN_URL": "postgresql://u:p@localhost:5432/postgres",
        "RAG_PUBLIC_URL": "http://localhost:8000",
        "REDIS_URL": "redis://localhost:6379/0",
    }
    base.update(overrides)
    return base


def test_dek_optional_when_absent(monkeypatch):
    for k, v in _base_env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("HARPOCRATE_DEK", raising=False)
    settings = Settings()
    assert settings.harpocrate_dek is None


def test_dek_accepts_32_chars(monkeypatch):
    for k, v in _base_env(HARPOCRATE_DEK="a" * 32).items():
        monkeypatch.setenv(k, v)
    settings = Settings()
    assert settings.harpocrate_dek is not None
    assert settings.harpocrate_dek.get_secret_value() == "a" * 32


def test_dek_under_32_chars_rejected(monkeypatch):
    for k, v in _base_env(HARPOCRATE_DEK="short").items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ValidationError, match="HARPOCRATE_DEK"):
        Settings()


def test_dek_empty_string_treated_as_none(monkeypatch):
    """HARPOCRATE_DEK= (vide) dans .env doit être équivalent à absent."""
    for k, v in _base_env(HARPOCRATE_DEK="").items():
        monkeypatch.setenv(k, v)
    settings = Settings()
    assert settings.harpocrate_dek is None


def test_harpocrate_api_keys_now_optional(monkeypatch):
    """Le validator strict de M4 est supprimé : un boot sans env Harpocrate doit
    être autorisé (la résolution échouera en runtime si aucun coffre n'est en DB)."""
    for k, v in _base_env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("HARPOCRATE_API_TOKEN_RAG", raising=False)
    monkeypatch.delenv("HARPOCRATE_API_URL_RAG", raising=False)
    settings = Settings()
    assert settings.harpocrate_api_keys == {}
