"""DTOs du partage d'endpoints (migration 095)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Borne la liste envoyée en un appel : au-delà, c'est `shared_with_all` qu'il faut.
_MAX_SHARE_USERS = 200


class ShareUser(BaseModel):
    """Utilisateur existant (bénéficiaire ou candidat au partage)."""

    id: UUID
    username: str
    email: str


class EndpointSharingOut(BaseModel):
    shared_with_all: bool
    users: list[ShareUser]


class EndpointSharingUpdate(BaseModel):
    """État de partage voulu, remplacé intégralement."""

    model_config = ConfigDict(extra="forbid")

    shared_with_all: bool
    user_ids: list[UUID] = Field(default_factory=list, max_length=_MAX_SHARE_USERS)


class ServiceModel(BaseModel):
    provider: str
    model: str


class UsableEndpointOut(BaseModel):
    """Endpoint utilisable pour créer un workspace — sans références de secrets.

    `access` : 'owned' (coffre possédé), 'default' (coffre par défaut de
    l'instance) ou 'shared' (partagé avec l'appelant ou avec tous).
    """

    id: UUID
    slug: str
    label: str
    vault_id: UUID
    vault_name: str
    vault_label: str
    access: Literal["owned", "default", "shared"]
    indexer: ServiceModel
    rerank: ServiceModel | None
    llm: ServiceModel | None
