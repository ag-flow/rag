from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

# Regex strictement aligné design 2026-05-15 :
# - commence par une lettre minuscule
# - suite : minuscules / chiffres / _ / -
# - longueur 1..63 (limite Postgres pour les identifiants de base, puisque
#   rag_<name> doit rester un identifiant DB valide).
_NAME_REGEX = r"^[a-z][a-z0-9_-]{0,62}$"


class IndexerSpec(BaseModel):
    """Indexeur d'un workspace : provider + modèle + api_key_ref (référence Harpocrate)."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key_ref: str | None = None
    base_url: str | None = None


class IndexerCreateSpec(BaseModel):
    """Indexeur pour la création d'un workspace.

    api_key_ref est le harpo_path d'une provider_api_key existante.
    Le backend ne stocke rien dans Harpocrate — il référence une clé déjà présente.
    """

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key_ref: str | None = None
    base_url: str | None = None


class RerankCreateSpec(BaseModel):
    """Config reranking à la création d'un workspace (immuable après)."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key_ref: str | None = None
    base_url: str | None = None
    top_k_pre_rerank: int = Field(default=50, gt=0, le=500)


class WorkspaceCreateRequest(BaseModel):
    """Payload POST /workspaces."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=_NAME_REGEX, max_length=63)
    indexer: IndexerCreateSpec
    rerank: RerankCreateSpec | None = None


class IndexerPatchSpec(BaseModel):
    """Sous-payload PATCH /workspaces/{name} : seul api_key_ref est modifiable."""

    model_config = ConfigDict(extra="forbid")

    api_key_ref: str = Field(min_length=1)


class WorkspacePatchRequest(BaseModel):
    """Payload PATCH /workspaces/{name}. Seul `indexer.api_key_ref` est modifiable."""

    model_config = ConfigDict(extra="forbid")

    indexer: IndexerPatchSpec


class WorkspaceResponse(BaseModel):
    """Réponse GET/POST /workspaces/{name}."""

    id: UUID
    name: str
    indexer: IndexerSpec
    sources_count: int
    documents_count: int
    last_indexed_at: str | None
    created_at: str


class WorkspaceCreateResponse(BaseModel):
    """Réponse 201 POST /workspaces — `api_key` en clair, exposée UNE FOIS."""

    id: UUID
    name: str
    api_key: str
    created_at: str


class ApiKeyRotateResponse(BaseModel):
    """Réponse POST /workspaces/{name}/rotate-apikey."""

    api_key: str


class SourceCreateRequest(BaseModel):
    """Payload POST /workspaces/{name}/sources."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[a-z0-9_-]+$")
    type: Literal["git"]
    git_provider: str | None = None
    auth_type: Literal["token", "ssh"] | None = None
    auth_ref: str | None = None
    ssh_key_ref: str | None = None
    ssh_username: str | None = None
    config: dict[str, Any]

    @field_validator("config")
    @classmethod
    def config_must_have_url(cls, v: dict[str, Any]) -> dict[str, Any]:
        if "url" not in v or not v["url"]:
            raise ValueError("config.url is required for git sources")
        return v


class SourceUpdateRequest(BaseModel):
    """Payload PATCH /workspaces/{name}/sources/{source_id}."""

    model_config = ConfigDict(extra="forbid")

    git_provider: str | None = None
    auth_type: Literal["token", "ssh"] | None = None
    auth_ref: str | None = None
    ssh_key_ref: str | None = None
    ssh_username: str | None = None
    config: dict[str, Any]


class SourceResponse(BaseModel):
    id: UUID
    name: str | None
    type: str
    config: dict[str, Any]
    webhook_enabled: bool = False
    last_indexed_at: str | None
    created_at: str
    branch_warning: str | None = None


class SourceTestResult(BaseModel):
    success: bool
    message: str | None = None


class ReindexRequest(BaseModel):
    """Payload POST /workspaces/{name}/reindex (body optionnel)."""

    model_config = ConfigDict(extra="forbid")

    indexer: IndexerSpec | None = None


class WebhookEnableResponse(BaseModel):
    """Retour de POST /workspaces/{name}/sources/{source}/webhook/enable."""

    source_name: str
    webhook_url: str
    secret: str


class JobResponse(BaseModel):
    id: UUID
    triggered_by: str
    status: str
    files_changed: int
    files_skipped: int
    error_message: str | None
    started_at: str | None
    finished_at: str | None
    duration_ms: int | None


class JobFileEntry(BaseModel):
    path: str
    change_type: Literal["added", "modified", "deleted"]


class JobFilesResponse(BaseModel):
    files: list[JobFileEntry]
    total: int
    limit: int


class ModelEntry(BaseModel):
    """Une entrée du registre model_dimensions."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    dimension: int = Field(gt=0)
    created_at: str | None = None


class RerankSpec(BaseModel):
    """Body PUT /workspaces/{name}/rerank."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    provider: Literal["cohere", "openai", "voyage", "ollama", "jina", "dashscope"]
    model: str = Field(min_length=1)
    api_key_ref: str | None = None
    base_url: str | None = None
    top_k_pre_rerank: int = Field(default=50, gt=0, le=500)


class RerankConfigResponse(BaseModel):
    """Réponse GET / PUT /workspaces/{name}/rerank."""

    workspace_id: UUID
    provider: str
    model: str
    api_key_ref: str | None
    base_url: str | None
    top_k_pre_rerank: int
    created_at: str
    updated_at: str


class HybridConfigSpec(BaseModel):
    enabled: bool = True
    rrf_k: int = Field(default=60, gt=0)
    fts_config: str = Field(default="simple", min_length=1, max_length=63)


class HybridConfigResponse(BaseModel):
    workspace_id: str
    enabled: bool
    rrf_k: int
    fts_config: str
    created_at: str
    updated_at: str


def _validate_markdown_extras(v: dict[str, Any]) -> dict[str, Any]:
    """Accepte uniquement {heading_levels?: list[int]}. Default si absent."""
    allowed_keys = {"heading_levels"}
    extra_keys = set(v.keys()) - allowed_keys
    if extra_keys:
        raise ValueError(
            f"markdown strategy only accepts {allowed_keys}, got unknown keys: {extra_keys}"
        )
    levels = v.get("heading_levels", [1, 2])
    if not isinstance(levels, list) or not levels:
        raise ValueError("heading_levels must be a non-empty list")
    if not all(isinstance(x, int) and 1 <= x <= 6 for x in levels):
        raise ValueError("heading_levels values must be integers in [1, 6]")
    if levels != sorted(levels):
        raise ValueError("heading_levels must be sorted ascending")
    if len(set(levels)) != len(levels):
        raise ValueError("heading_levels must not contain duplicates")
    return {"heading_levels": levels}


class ChunkingConfigSpec(BaseModel):
    """Payload PUT /workspaces/{name}/chunking-config."""

    model_config = ConfigDict(extra="forbid")

    strategy: Literal["paragraph", "markdown"]
    max_chars: int = Field(gt=0)
    min_chars: int = Field(ge=0)
    overlap_chars: int = Field(ge=0)
    extras: dict[str, Any] = Field(default_factory=dict)

    @field_validator("min_chars")
    @classmethod
    def _min_lt_max(cls, v: int, info: ValidationInfo) -> int:
        max_chars = info.data.get("max_chars")
        if max_chars is not None and v >= max_chars:
            raise ValueError("min_chars must be < max_chars")
        return v

    @field_validator("overlap_chars")
    @classmethod
    def _overlap_lt_max(cls, v: int, info: ValidationInfo) -> int:
        max_chars = info.data.get("max_chars")
        if max_chars is not None and v >= max_chars:
            raise ValueError("overlap_chars must be < max_chars")
        return v

    @field_validator("extras")
    @classmethod
    def _validate_extras(cls, v: dict[str, Any], info: ValidationInfo) -> dict[str, Any]:
        strategy = info.data.get("strategy")
        if strategy == "paragraph":
            if v:
                raise ValueError("extras must be empty for strategy 'paragraph'")
            return v
        if strategy == "markdown":
            return _validate_markdown_extras(v)
        return v


class EngineSpec(BaseModel):
    """Payload PUT /workspaces/{name}/chunking-config/engine."""

    model_config = ConfigDict(extra="forbid")

    engine: Literal["legacy", "structured"]


class EngineResponse(BaseModel):
    """Réponse bascule moteur sans réindexation (0 doc indexé)."""

    workspace_id: UUID
    engine: str


class ChunkingConfigResponse(BaseModel):
    """Réponse GET /workspaces/{name}/chunking-config."""

    workspace_id: UUID
    strategy: str
    max_chars: int
    min_chars: int
    overlap_chars: int
    extras: dict[str, Any]
    created_at: str
    updated_at: str
