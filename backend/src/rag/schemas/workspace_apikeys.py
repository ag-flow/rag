from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    fingerprint_preview: str
    api_key_ref: str
    status: str
    created_at: datetime
    revoked_at: datetime | None
    rotated_at: datetime | None


class ApiKeyCreated(BaseModel):
    id: UUID
    name: str
    fingerprint_preview: str
    api_key: str
    created_at: datetime


class ApiKeyRotated(BaseModel):
    new_key_id: UUID
    new_api_key: str
    new_fingerprint_preview: str
    old_key_id: UUID
    grace_until: datetime
