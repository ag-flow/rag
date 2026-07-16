from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceGrantIn(BaseModel):
    """Droit accordé à une clé sur un workspace."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    can_read: bool = True
    can_write: bool = False


class UserApiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    workspaces: list[WorkspaceGrantIn] = Field(default_factory=list)


class GrantsUpdate(BaseModel):
    """Remplace l'ensemble des grants d'une clé."""

    model_config = ConfigDict(extra="forbid")

    workspaces: list[WorkspaceGrantIn]


class WorkspaceGrantOut(BaseModel):
    workspace_id: UUID
    workspace_name: str
    can_read: bool
    can_write: bool


class UserApiKeyOut(BaseModel):
    id: UUID
    name: str
    fingerprint_preview: str
    status: str
    created_at: datetime
    revoked_at: datetime | None
    rotated_at: datetime | None
    workspaces: list[WorkspaceGrantOut]


class UserApiKeyCreated(BaseModel):
    """Réponse de création — seule occasion où la clé apparaît en clair."""

    id: UUID
    name: str
    api_key: str
    fingerprint_preview: str
    created_at: datetime


class UserApiKeyRotated(BaseModel):
    new_key_id: UUID
    new_api_key: str
    new_fingerprint_preview: str
    old_key_id: UUID
    grace_until: datetime
