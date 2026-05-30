from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import (
    AnyHttpUrl,
    Field,
    PostgresDsn,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration applicative — lue depuis le .env + env vars.

    Depuis M5c, les coffres Harpocrate sont configurables exclusivement
    via l'IHM /ui/settings/harpocrate-vaults (table harpocrate_vaults).
    Aucune variable d'env HARPOCRATE_API_TOKEN_* / HARPOCRATE_API_URL_*
    n'est lue au boot.
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

    pricing_file: Path = Field(
        default=Path("/app/config/pricing.yml"),
        description="Chemin du fichier YAML de tarifs providers d'embedding.",
    )

    harpocrate_dek: SecretStr | None = Field(
        default=None,
        description="Passphrase pgcrypto pour chiffrer les api_keys en DB. "
        "Min 32 chars. Requis dès qu'un coffre est créé.",
    )

    rag_bootstrap_admin_username: str = "admin"
    rag_bootstrap_admin_email: str = "admin@rag.io"
    rag_bootstrap_admin_password_hash: str = ""
    rag_bootstrap_session_ttl_seconds: int = Field(default=28800, ge=60)

    @property
    def bootstrap_enabled(self) -> bool:
        return bool(self.rag_bootstrap_admin_password_hash.strip())

    rag_session_secret: SecretStr = SecretStr("")

    rag_webhook_secret: SecretStr | None = Field(
        default=None,
        description="Secret HMAC pour signer les payloads webhook (X-RAG-Signature). "
        "Optionnel — si absent, la signature est omise (warning au dispatch).",
    )

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
