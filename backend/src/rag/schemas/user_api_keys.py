from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Niveau d'accès d'une clé (migration 067) — appliqué à TOUS les workspaces :
#   read       : recherche / lecture MCP
#   read_write : + indexation / push
#   admin      : + ressources hors workspace (bibliothèque), isolées par owner
KeyScope = Literal["read", "read_write", "admin"]


class UserApiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    scope: KeyScope = "read"
    # Exiger une identité humaine signée (OBO) sur chaque appel — fail closed.
    require_obo: bool = False


class ScopeUpdate(BaseModel):
    """Change le niveau d'accès d'une clé."""

    model_config = ConfigDict(extra="forbid")

    scope: KeyScope


class UserApiKeyUpdate(BaseModel):
    """Modification partielle d'une clé, appliquée en UNE écriture.

    Niveau et exigence OBO ensemble : deux appels successifs pouvaient n'en
    appliquer qu'un et laisser croire l'OBO activé alors qu'il ne l'est pas.
    """

    model_config = ConfigDict(extra="forbid")

    scope: KeyScope | None = None
    require_obo: bool | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> UserApiKeyUpdate:
        if self.scope is None and self.require_obo is None:
            raise ValueError("au moins un champ parmi scope, require_obo")
        return self


class UserApiKeyOut(BaseModel):
    id: UUID
    name: str
    fingerprint_preview: str
    status: str
    scope: KeyScope
    require_obo: bool
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
    require_obo: bool
    created_at: datetime


class UserApiKeyRotated(BaseModel):
    new_key_id: UUID
    new_api_key: str
    new_fingerprint_preview: str
    old_key_id: UUID
    grace_until: datetime
