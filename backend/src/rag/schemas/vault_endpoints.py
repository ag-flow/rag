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
    # Requêtes parallèles max vers ce service — appliqué au niveau ENDPOINT,
    # agrégé cross-workspace (enabler a7e2ec90). NULL = pas de limite.
    max_concurrency: int | None = Field(default=None, ge=1)


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
    # Requêtes parallèles max vers ce service — appliqué au niveau ENDPOINT,
    # agrégé cross-workspace (enabler a7e2ec90). NULL = pas de limite.
    max_concurrency: int | None = Field(default=None, ge=1)


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
    # Requêtes parallèles max vers ce service — appliqué au niveau ENDPOINT,
    # agrégé cross-workspace (enabler a7e2ec90). NULL = pas de limite.
    max_concurrency: int | None = Field(default=None, ge=1)


class EndpointCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=128)
    indexer: EndpointIndexerSpec
    rerank: EndpointRerankSpec | None = None
    llm: EndpointLlmSpec | None = None


class EndpointUpdate(BaseModel):
    """Le slug est figé à la création ; label et configs restent éditables.

    Snapshot : la modification n'affecte que les workspaces créés ensuite.
    Le fallback (même coffre, un seul niveau, vectorisation compatible) et les
    paramètres du breaker se règlent ici — `clear_fallback` retire le lien.
    """

    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=128)
    indexer: EndpointIndexerSpec | None = None
    rerank: EndpointRerankSpec | None = None
    clear_rerank: bool = False
    llm: EndpointLlmSpec | None = None
    clear_llm: bool = False
    fallback_endpoint_id: UUID | None = None
    clear_fallback: bool = False
    failure_threshold: int | None = Field(default=None, ge=1, le=100)
    cooldown_seconds: int | None = Field(default=None, ge=1, le=3600)


class EndpointOut(BaseModel):
    id: UUID
    vault_id: UUID
    label: str
    slug: str
    indexer: EndpointIndexerSpec
    rerank: EndpointRerankSpec | None
    llm: EndpointLlmSpec | None
    fallback_endpoint_id: UUID | None = None
    failure_threshold: int = 3
    cooldown_seconds: int = 60
    created_at: datetime
    updated_at: datetime
