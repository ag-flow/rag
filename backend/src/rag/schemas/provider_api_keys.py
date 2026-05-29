from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_KEY_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


class ProviderApiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=4096)

    @field_validator("key_id")
    @classmethod
    def _v_key_id(cls, v: str) -> str:
        if not _KEY_ID_RE.match(v):
            raise ValueError("key_id doit matcher ^[a-zA-Z0-9_-]+$")
        return v


class ProviderApiKeyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=128)
    value: str | None = Field(default=None, min_length=1, max_length=4096)


class ProviderApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key_id: str
    label: str
    provider: str
    harpo_path: str
    created_at: datetime
