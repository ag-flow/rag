from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_KEY_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

SshKeyType = Literal["ed25519", "rsa-4096", "ecdsa-256"]


class SshKeyImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    private_key: str = Field(min_length=1)
    public_key: str = Field(min_length=1)
    passphrase: str | None = Field(default=None)

    @field_validator("key_id")
    @classmethod
    def _v_key_id(cls, v: str) -> str:
        if not _KEY_ID_RE.match(v):
            raise ValueError("key_id doit matcher ^[a-zA-Z0-9_-]+$")
        return v


class SshKeyGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    key_type: SshKeyType

    @field_validator("key_id")
    @classmethod
    def _v_key_id(cls, v: str) -> str:
        if not _KEY_ID_RE.match(v):
            raise ValueError("key_id doit matcher ^[a-zA-Z0-9_-]+$")
        return v


class SshKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key_id: str
    name: str
    key_type: str
    public_key: str
    passphrase_protected: bool
    harpo_path: str
    created_at: datetime
