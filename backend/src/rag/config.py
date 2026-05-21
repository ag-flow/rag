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
    via un model_validator. Aucune paire n'est requise au boot ; la
    vérification de la disponibilité d'un coffre est déléguée au runtime
    (résolution via DB ou env selon le composant appelant).
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

    harpocrate_dek: SecretStr | None = Field(
        default=None,
        description="Passphrase pgcrypto pour chiffrer les api_keys en DB. "
        "Min 32 chars. Requis dès qu'un coffre est créé.",
    )

    api_key_dek: str | None = Field(default=None, alias="RAG_API_KEY_DEK")

    rag_bootstrap_admin_username: str = "admin"
    rag_bootstrap_admin_password_hash: str = ""
    rag_bootstrap_session_ttl_seconds: int = Field(default=28800, ge=60)

    @property
    def bootstrap_enabled(self) -> bool:
        return bool(self.rag_bootstrap_admin_password_hash.strip())

    rag_session_secret: SecretStr = SecretStr("")

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

    @field_validator("harpocrate_dek")
    @classmethod
    def _validate_harpocrate_dek_length(cls, v: SecretStr | None) -> SecretStr | None:
        if v is None:
            return None
        raw = v.get_secret_value()
        # Une valeur vide (HARPOCRATE_DEK= dans .env) est traitée comme absente —
        # le DEK est optionnel tant qu'aucun coffre n'est créé en DB.
        if raw == "":
            return None
        if len(raw) < 32:
            raise ValueError("HARPOCRATE_DEK doit faire au moins 32 caractères")
        return v

    @field_validator("api_key_dek")
    @classmethod
    def _validate_api_key_dek(cls, v: str | None) -> str | None:
        # Une valeur vide (RAG_API_KEY_DEK= dans .env) est traitée comme absente —
        # symétrique au comportement HARPOCRATE_DEK.
        if not v:
            return None
        if len(v) < 32:
            raise ValueError("RAG_API_KEY_DEK doit faire au moins 32 caractères")
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
            # Aucune paire env Harpocrate déclarée : on tolère ce cas au boot,
            # la résolution effective d'un coffre est déléguée aux composants
            # runtime (DB-first, env-fallback). `harpocrate_api_keys` reste {}.
            return data

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

    @model_validator(mode="after")
    def fill_session_secret_fallback(self) -> Settings:
        """`RAG_SESSION_SECRET` (32+ chars) signe les cookies `_oidc_session`.

        Fallback dev : si absent, utilise `RAG_MASTER_KEY` (qui doit alors
        etre lui-meme >= 32 chars). En prod, fournir explicitement
        `RAG_SESSION_SECRET=<openssl rand -hex 32>`.
        """
        if not self.rag_session_secret.get_secret_value():
            self.rag_session_secret = self.rag_master_key
        if len(self.rag_session_secret.get_secret_value()) < 32:
            raise ValueError(
                "RAG_SESSION_SECRET must be >= 32 chars "
                "(use `openssl rand -hex 32` to generate one)"
            )
        return self
