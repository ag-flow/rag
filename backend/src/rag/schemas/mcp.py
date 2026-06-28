from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_QUERY_MAX_LEN = 2000
_TOP_K_MAX = 50
_API_KEY_MAX = 128
_WORKSPACE_NAME_REGEX = r"^[a-z][a-z0-9_-]{0,62}$"


class _McpRequestBase(BaseModel):
    """Champs communs single+multi. `extra="forbid"` rejette un payload
    qui mixe `workspace` + `workspaces` (sinon le champ "en trop" passerait
    silencieusement dans l'un des variants)."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=_QUERY_MAX_LEN)
    top_k: int = Field(default=5, ge=1, le=_TOP_K_MAX)
    min_score: float = Field(default=0.3, ge=-1.0, le=1.0)


class SingleWorkspaceRequest(_McpRequestBase):
    workspace: str = Field(..., pattern=_WORKSPACE_NAME_REGEX)
    api_key: str = Field(..., min_length=1, max_length=_API_KEY_MAX)


class _McpWorkspaceRef(BaseModel):
    """Item de la liste `workspaces` côté MultiWorkspaceRequest."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., pattern=_WORKSPACE_NAME_REGEX)
    api_key: str = Field(..., min_length=1, max_length=_API_KEY_MAX)


class MultiWorkspaceRequest(_McpRequestBase):
    workspaces: list[_McpWorkspaceRef] = Field(..., min_length=1, max_length=10)


# Union Pydantic v2 smart-mode : tente Single puis Multi (ou l'inverse) et
# garde le variant qui matche le mieux. `extra="forbid"` garantit qu'un
# payload mixte ne matche aucun.
McpRequest = SingleWorkspaceRequest | MultiWorkspaceRequest


class DebugTrace(BaseModel):
    """Trace de debug d'un hit hybride. Peuplée uniquement si debug=True."""

    vector_rank: int | None = None
    vector_score: float | None = None
    lexical_rank: int | None = None
    lexical_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None  # null jusqu'à ce que le reranker expose les scores
    final_rank: int | None = None


class SearchHit(BaseModel):
    workspace: str
    indexer: str
    path: str
    chunk_index: int
    content: str
    score: float
    metadata: dict[str, Any] | None = None
    enrichment_key: str | None = None
    source_path: str | None = None
    debug: DebugTrace | None = None


class McpResponse(BaseModel):
    query: str
    results: list[SearchHit]
