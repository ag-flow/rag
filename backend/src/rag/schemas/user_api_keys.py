from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Niveau d'accès d'une clé (migration 067) — appliqué à TOUS les workspaces :
#   read       : recherche / lecture MCP
#   read_write : + indexation / push
#   admin      : + ressources hors workspace (bibliothèque), isolées par owner
KeyScope = Literal["read", "read_write", "admin"]


class UserApiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    scope: KeyScope = "read"


class ScopeUpdate(BaseModel):
    """Change le niveau d'accès d'une clé."""

    model_config = ConfigDict(extra="forbid")

    scope: KeyScope


class UserApiKeyOut(BaseModel):
    id: UUID
    name: str
    fingerprint_preview: str
    status: str
    scope: KeyScope
    created_at: datetime
    revoked_at: datetime | None
    rotated_at: datetime | None


class UserApiKeyCreated(BaseModel):
    """Réponse de création — seule occasion où la clé apparaît en clair."""

    id: UUID
    name: str
    api_key: str
    fingerprint_preview: str
    scope: KeyScope
    created_at: datetime


class UserApiKeyRotated(BaseModel):
    new_key_id: UUID
    new_api_key: str
    new_fingerprint_preview: str
    old_key_id: UUID
    grace_until: datetime
