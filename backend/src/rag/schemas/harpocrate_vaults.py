from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
_PROBE_RE = re.compile(r"^[a-zA-Z0-9_/-]+$")


class VaultSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    label: str
    base_url: str
    api_key_id: str
    probe_path: str | None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class VaultCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=8, max_length=512)
    api_key_id: str = Field(min_length=1, max_length=128)
    api_key: str = Field(min_length=8, max_length=2048)
    probe_path: str | None = None
    is_default: bool = False

    @field_validator("name")
    @classmethod
    def _v_name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError("name doit matcher ^[a-z][a-z0-9_-]{2,63}$")
        return v

    @field_validator("base_url")
    @classmethod
    def _v_base_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url doit commencer par http:// ou https://")
        return v.rstrip("/")

    @field_validator("probe_path")
    @classmethod
    def _v_probe_path(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _PROBE_RE.match(v):
            raise ValueError("probe_path : caractères autorisés [a-zA-Z0-9_/-]")
        return v


class VaultUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = Field(default=None, min_length=8, max_length=512)
    probe_path: str | None = Field(default=None, max_length=512)

    @field_validator("base_url")
    @classmethod
    def _v_base_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url doit commencer par http:// ou https://")
        return v.rstrip("/")

    @field_validator("probe_path")
    @classmethod
    def _v_probe_path(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _PROBE_RE.match(v):
            raise ValueError("probe_path : caractères autorisés [a-zA-Z0-9_/-]")
        return v


class VaultRotateApiKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key_id: str = Field(min_length=1, max_length=128)
    api_key: str = Field(min_length=8, max_length=2048)


class VaultTestConnectionResult(BaseModel):
    ok: bool
    detail: str
    probe_path_used: str


class VaultRevealApiKeyResponse(BaseModel):
    id: UUID
    api_key_id: str
    api_key: str


class WalletInfoResponse(BaseModel):
    """Métadonnées du coffre Harpocrate (combinaison whoami + info)."""

    wallet_id: UUID
    wallet_name: str | None
    api_key_id: str
    permissions: list[str]
    api_key_expires_at: datetime | None


class SecretTypeSummary(BaseModel):
    """Résumé d'un type du catalogue Harpocrate."""

    type_uuid: UUID
    type: str
    sous_type: str | None
    label: str
    deprecated: bool


class SecretListItem(BaseModel):
    """Résumé d'un secret du wallet (sans valeur)."""

    id: UUID
    name: str
    description: str | None
    is_placeholder: bool
    tags: list[str]


class SecretListResponse(BaseModel):
    """Réponse paginée du listing des secrets."""

    secrets: list[SecretListItem]
    next_cursor: str | None
