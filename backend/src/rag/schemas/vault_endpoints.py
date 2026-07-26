from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from rag.schemas.slug import slugify

# Ré-export : la dérivation de slug est devenue transverse (endpoints de
# coffre, stratégies de chunking) et vit dans `rag.schemas.slug`.
__all__ = [
    "EndpointCreate",
    "EndpointIndexerSpec",
    "EndpointLlmSpec",
    "EndpointOut",
    "EndpointRerankSpec",
    "EndpointUpdate",
    "slugify",
]


class EndpointIndexerSpec(BaseModel):
    """Vectorisation : provider + modèle + clé API (harpo_path du coffre) + URL."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    api_key_ref: str | None = None
    base_url: str | None = None
    # Limites de débit du service (NULL = règle désactivée). Copiées dans la
    # config workspace à la création et au refresh.
    rpm_limit: int | None = Field(default=None, ge=1)
    tpm_limit: int | None = Field(default=None, ge=1)


class EndpointRerankSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    api_key_ref: str | None = None
    base_url: str | None = None
    top_k_pre_rerank: int = Field(default=20, ge=1, le=200)
    # Limites de débit du service (NULL = règle désactivée). Copiées dans la
    # config workspace à la création et au refresh.
    rpm_limit: int | None = Field(default=None, ge=1)
    tpm_limit: int | None = Field(default=None, ge=1)


class EndpointLlmSpec(BaseModel):
    """LLM d'exécution des prompts (enrichissements, contexte, chat Playground).

    Copié dans workspace_llm_configs à la création du workspace (snapshot,
    même modèle que l'indexeur et le rerank)."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    api_key_ref: str | None = None
    base_url: str | None = None
    # Limites de débit du service (NULL = règle désactivée). Copiées dans la
    # config workspace à la création et au refresh.
    rpm_limit: int | None = Field(default=None, ge=1)
    tpm_limit: int | None = Field(default=None, ge=1)


class EndpointCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=128)
    indexer: EndpointIndexerSpec
    rerank: EndpointRerankSpec | None = None
    llm: EndpointLlmSpec | None = None


class EndpointUpdate(BaseModel):
    """Le slug est figé à la création ; label et configs restent éditables.

    Snapshot : la modification n'affecte que les workspaces créés ensuite.
    """

    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=128)
    indexer: EndpointIndexerSpec | None = None
    rerank: EndpointRerankSpec | None = None
    clear_rerank: bool = False
    llm: EndpointLlmSpec | None = None
    clear_llm: bool = False


class EndpointOut(BaseModel):
    id: UUID
    vault_id: UUID
    label: str
    slug: str
    indexer: EndpointIndexerSpec
    rerank: EndpointRerankSpec | None
    llm: EndpointLlmSpec | None
    created_at: datetime
    updated_at: datetime
