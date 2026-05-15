from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.schemas.admin import (
    IndexerSpec,
    ModelEntry,
    SourceCreateRequest,
    WorkspaceCreateRequest,
    WorkspacePatchRequest,
)

# WorkspaceCreateRequest -------------------------------------------------------


def test_workspace_create_valid_minimal() -> None:
    req = WorkspaceCreateRequest.model_validate(
        {
            "name": "harpocrate",
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        }
    )
    assert req.name == "harpocrate"
    assert req.indexer.provider == "openai"


def test_workspace_create_name_regex_rejects_uppercase() -> None:
    with pytest.raises(ValidationError, match="name"):
        WorkspaceCreateRequest.model_validate(
            {
                "name": "Harpocrate",
                "indexer": {
                    "provider": "openai",
                    "model": "text-embedding-3-small",
                    "api_key_ref": "k",
                },
            }
        )


def test_workspace_create_name_regex_rejects_leading_digit() -> None:
    with pytest.raises(ValidationError, match="name"):
        WorkspaceCreateRequest.model_validate(
            {
                "name": "1abc",
                "indexer": {
                    "provider": "openai",
                    "model": "text-embedding-3-small",
                    "api_key_ref": "k",
                },
            }
        )


def test_workspace_create_name_max_length_63() -> None:
    long = "a" + "b" * 63  # 64 chars
    with pytest.raises(ValidationError, match="name"):
        WorkspaceCreateRequest.model_validate(
            {
                "name": long,
                "indexer": {
                    "provider": "openai",
                    "model": "text-embedding-3-small",
                    "api_key_ref": "k",
                },
            }
        )


def test_workspace_create_name_accepts_dash_and_underscore() -> None:
    req = WorkspaceCreateRequest.model_validate(
        {
            "name": "ag-flow_docker",
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "k",
            },
        }
    )
    assert req.name == "ag-flow_docker"


def test_workspace_create_rejects_extra_fields() -> None:
    # Garantit que rag.cnx/base n'est pas accepté côté input
    # (le service les dérive du nom). Pydantic v2 strict.
    with pytest.raises(ValidationError):
        WorkspaceCreateRequest.model_validate(
            {
                "name": "ws",
                "indexer": {
                    "provider": "openai",
                    "model": "text-embedding-3-small",
                    "api_key_ref": "k",
                },
                "rag": {"cnx": "postgresql://x@y/z", "base": "z"},
            }
        )


# IndexerSpec ------------------------------------------------------------------


def test_indexer_spec_requires_provider_and_model() -> None:
    with pytest.raises(ValidationError):
        IndexerSpec.model_validate({"api_key_ref": "k"})


def test_indexer_spec_api_key_ref_optional_for_ollama_in_schema() -> None:
    # Le schéma accepte api_key_ref=None ; la validation métier (eager Harpocrate)
    # se fera au service en sautant Ollama si la ref est None.
    spec = IndexerSpec.model_validate(
        {"provider": "ollama", "model": "nomic-embed-text", "api_key_ref": None}
    )
    assert spec.api_key_ref is None


# WorkspacePatchRequest -------------------------------------------------------


def test_workspace_patch_only_allows_indexer_api_key_ref() -> None:
    req = WorkspacePatchRequest.model_validate({"indexer": {"api_key_ref": "new_key"}})
    assert req.indexer is not None
    assert req.indexer.api_key_ref == "new_key"


def test_workspace_patch_rejects_indexer_provider_change() -> None:
    with pytest.raises(ValidationError):
        WorkspacePatchRequest.model_validate({"indexer": {"provider": "voyage"}})


def test_workspace_patch_rejects_top_level_extra() -> None:
    with pytest.raises(ValidationError):
        WorkspacePatchRequest.model_validate({"name": "newname"})


# SourceCreateRequest ---------------------------------------------------------


def test_source_create_git_minimal() -> None:
    req = SourceCreateRequest.model_validate(
        {
            "type": "git",
            "config": {
                "url": "https://github.com/gael/harpocrate",
                "branch": "main",
                "auth_ref": "github_token",
                "include": ["**/*.md"],
                "exclude": [],
            },
        }
    )
    assert req.type == "git"
    assert req.config["url"] == "https://github.com/gael/harpocrate"


def test_source_create_rejects_non_git_type() -> None:
    with pytest.raises(ValidationError, match="git"):
        SourceCreateRequest.model_validate(
            {
                "type": "confluence",
                "config": {"url": "https://wiki.example.com"},
            }
        )


# ModelEntry ------------------------------------------------------------------


def test_model_entry_dimension_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ModelEntry.model_validate({"provider": "p", "model": "m", "dimension": 0})
