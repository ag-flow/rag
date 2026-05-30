from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_KEY_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

GitHost = Literal["github", "gitlab", "gitea", "bitbucket", "azure-devops"]


class GitCredentialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    host: GitHost
    scope_url: str | None = Field(default=None, max_length=512)
    value: str = Field(min_length=1, max_length=4096)
    valid_days: int | None = Field(default=None, ge=1)

    @field_validator("key_id")
    @classmethod
    def _v_key_id(cls, v: str) -> str:
        if not _KEY_ID_RE.match(v):
            raise ValueError("key_id doit matcher ^[a-zA-Z0-9_-]+$")
        return v


class GitCredentialUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=128)
    scope_url: str | None = Field(default=None, max_length=512)
    value: str | None = Field(default=None, min_length=1, max_length=4096)
    valid_days: int | None = Field(default=None, ge=1)


class GitCredentialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key_id: str
    label: str
    host: GitHost
    scope_url: str | None
    harpo_path: str
    expires_at: datetime | None
    created_at: datetime


class GitCredentialWithVault(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key_id: str
    label: str
    host: str
    harpo_path: str
    vault_name: str
    vault_label: str
    created_at: datetime
