from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    Field,
    PostgresDsn,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class HarpocrateClientConfig(BaseModel):
    """Configuration d'une API key Harpocrate (identifiant logique → url + token)."""

    url: AnyHttpUrl
    token: SecretStr


class Settings(BaseSettings):
    """Configuration applicative — lue depuis le .env + env vars.

    Les paires HARPOCRATE_API_TOKEN_<ID> / HARPOCRATE_API_URL_<ID> sont
    consolidées dans `harpocrate_api_keys: dict[str, HarpocrateClientConfig]`
    via un model_validator. Au moins une paire est requise.
    """

    database_url: PostgresDsn
    rag_postgres_admin_url: PostgresDsn
    rag_master_key: SecretStr
    rag_public_url: AnyHttpUrl

    environment: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"
    sync_worker_poll_interval_seconds: int = 30

    # Interval par défaut entre 2 syncs d'une même source (override possible
    # par source via config.sync_interval_seconds). 5 min = bon compromis
    # entre fraicheur et coût bande passante GitHub.
    sync_default_interval_seconds: int = Field(default=300, ge=60)

    # Racine des clones git locaux. En prod : volume Docker named `rag_repos`
    # monté sur /var/lib/rag/repos. En test : `tmp_path` via fixture pytest.
    sync_repos_root: Path = Path("/var/lib/rag/repos")

    harpocrate_api_keys: dict[str, HarpocrateClientConfig] = {}

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("rag_master_key")
    @classmethod
    def master_key_non_empty(cls, v: SecretStr) -> SecretStr:
        if not v.get_secret_value().strip():
            raise ValueError("RAG_MASTER_KEY must not be empty")
        return v

    @model_validator(mode="before")
    @classmethod
    def collect_harpocrate_keys(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        keys: dict[str, dict[str, str]] = {}
        for env_key, env_value in os.environ.items():
            upper = env_key.upper()
            if upper.startswith("HARPOCRATE_API_TOKEN_"):
                identifier = upper.removeprefix("HARPOCRATE_API_TOKEN_").lower()
                keys.setdefault(identifier, {})["token"] = env_value
            elif upper.startswith("HARPOCRATE_API_URL_"):
                identifier = upper.removeprefix("HARPOCRATE_API_URL_").lower()
                keys.setdefault(identifier, {})["url"] = env_value

        if not keys:
            raise ValueError(
                "No Harpocrate API key configured — set HARPOCRATE_API_TOKEN_<ID> "
                "and HARPOCRATE_API_URL_<ID> (at least one pair)."
            )

        for identifier, parts in keys.items():
            if "token" not in parts:
                raise ValueError(
                    f"HARPOCRATE_API_TOKEN_{identifier.upper()} declared without "
                    f"matching HARPOCRATE_API_URL_{identifier.upper()}"
                )
            if "url" not in parts:
                raise ValueError(
                    f"HARPOCRATE_API_URL_{identifier.upper()} declared without "
                    f"matching HARPOCRATE_API_TOKEN_{identifier.upper()}"
                )

        data["harpocrate_api_keys"] = {
            identifier: {"url": parts["url"], "token": parts["token"]}
            for identifier, parts in keys.items()
        }
        return data
