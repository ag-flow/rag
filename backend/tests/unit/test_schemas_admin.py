from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.schemas.admin import (
    IndexerCreateSpec,
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
            "name": "workspace1",
            "label": "Workspace 1",
            "endpoint_id": "11111111-2222-3333-4444-555555555555",
        }
    )
    assert req.name == "workspace1"
    assert req.label == "Workspace 1"
    assert req.description == ""
    assert str(req.endpoint_id) == "11111111-2222-3333-4444-555555555555"


def test_workspace_create_carries_label_and_description() -> None:
    req = WorkspaceCreateRequest.model_validate(
        {
            "name": "workspace1",
            "label": "Mon workspace",
            "description": "Corpus de la doc interne",
            "endpoint_id": "11111111-2222-3333-4444-555555555555",
        }
    )
    assert req.label == "Mon workspace"
    assert req.description == "Corpus de la doc interne"


def test_workspace_create_rejects_empty_label() -> None:
    with pytest.raises(ValidationError, match="label"):
        WorkspaceCreateRequest.model_validate(
            {
                "name": "workspace1",
                "label": "",
                "endpoint_id": "11111111-2222-3333-4444-555555555555",
            }
        )


def test_workspace_create_resolved_ollama_no_api_key() -> None:
    from rag.schemas.admin import WorkspaceCreateResolved

    req = WorkspaceCreateResolved.model_validate(
        {
            "name": "myws",
            "label": "My WS",
            "indexer": {"provider": "ollama", "model": "nomic-embed-text"},
        }
    )
    assert req.indexer.api_key_ref is None


def test_workspace_create_name_regex_rejects_uppercase() -> None:
    with pytest.raises(ValidationError, match="name"):
        WorkspaceCreateRequest.model_validate(
            {
                "name": "Harpocrate",
                "label": "Harpocrate",
                "endpoint_id": "11111111-2222-3333-4444-555555555555",
            }
        )


def test_workspace_create_name_regex_rejects_leading_digit() -> None:
    with pytest.raises(ValidationError, match="name"):
        WorkspaceCreateRequest.model_validate(
            {
                "name": "1abc",
                "label": "1abc",
                "endpoint_id": "11111111-2222-3333-4444-555555555555",
            }
        )


def test_workspace_create_name_max_length_63() -> None:
    long = "a" + "b" * 63  # 64 chars
    with pytest.raises(ValidationError, match="name"):
        WorkspaceCreateRequest.model_validate(
            {
                "name": long,
                "label": "long",
                "endpoint_id": "11111111-2222-3333-4444-555555555555",
            }
        )


def test_workspace_create_name_accepts_exactly_63_chars() -> None:
    name_63 = "a" + "b" * 62  # exactement 63 chars
    req = WorkspaceCreateRequest.model_validate(
        {
            "name": name_63,
            "label": "long name",
            "endpoint_id": "11111111-2222-3333-4444-555555555555",
        }
    )
    assert req.name == name_63
    assert len(req.name) == 63


def test_workspace_create_name_accepts_dash_and_underscore() -> None:
    req = WorkspaceCreateRequest.model_validate(
        {
            "name": "ag-flow_docker",
            "label": "ag-flow docker",
            "endpoint_id": "11111111-2222-3333-4444-555555555555",
        }
    )
    assert req.name == "ag-flow_docker"


def test_workspace_create_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        WorkspaceCreateRequest.model_validate(
            {
                "name": "ws",
                "label": "ws",
                "endpoint_id": "11111111-2222-3333-4444-555555555555",
                "rag": {"cnx": "postgresql://x@y/z", "base": "z"},
            }
        )


# IndexerSpec (lecture/réponse) ------------------------------------------------


def test_indexer_spec_requires_provider_and_model() -> None:
    with pytest.raises(ValidationError):
        IndexerSpec.model_validate({"api_key_ref": "k"})


def test_indexer_spec_api_key_ref_optional() -> None:
    spec = IndexerSpec.model_validate(
        {"provider": "ollama", "model": "nomic-embed-text", "api_key_ref": None}
    )
    assert spec.api_key_ref is None


# IndexerCreateSpec (création) -------------------------------------------------


def test_indexer_create_spec_api_key_ref_optional_for_ollama() -> None:
    spec = IndexerCreateSpec.model_validate(
        {"provider": "ollama", "model": "nomic-embed-text"}
    )
    assert spec.api_key_ref is None


def test_indexer_create_spec_accepts_api_key_ref() -> None:
    # api_key_ref (harpo_path d'une provider_api_key existante) est le mécanisme
    # de clé à la création.
    spec = IndexerCreateSpec.model_validate(
        {"provider": "openai", "model": "text-embedding-3-small", "api_key_ref": "openai/k"}
    )
    assert spec.api_key_ref == "openai/k"


def test_indexer_create_spec_rejects_plaintext_api_key() -> None:
    # L'ancien champ `api_key` en clair n'est plus accepté (extra="forbid") :
    # la clé passe par référence Harpocrate via api_key_ref.
    with pytest.raises(ValidationError):
        IndexerCreateSpec.model_validate(
            {"provider": "openai", "model": "text-embedding-3-small", "api_key": "sk-abc123"}
        )


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
            "name": "harpocrate",
            "type": "git",
            "auth_type": "token",
            "auth_ref": "rag/github-pat",
            "config": {
                "url": "https://github.com/gael/harpocrate",
                "branch": "main",
                "include": ["**/*.md"],
                "exclude": [],
            },
        }
    )
    assert req.type == "git"
    assert req.config["url"] == "https://github.com/gael/harpocrate"
    assert req.name == "harpocrate"
    assert req.auth_type == "token"
    assert req.auth_ref == "rag/github-pat"


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


def test_model_entry_embedding_requires_dimension() -> None:
    with pytest.raises(ValidationError):
        ModelEntry.model_validate({"provider": "p", "model": "m", "kind": "embedding"})


def test_model_entry_llm_and_rerank_reject_dimension() -> None:
    for kind in ("llm", "rerank"):
        with pytest.raises(ValidationError):
            ModelEntry.model_validate(
                {"provider": "p", "model": "m", "kind": kind, "dimension": 1024}
            )


def test_model_entry_llm_and_rerank_valid_without_dimension() -> None:
    for kind in ("llm", "rerank"):
        entry = ModelEntry.model_validate({"provider": "p", "model": "m", "kind": kind})
        assert entry.kind == kind
        assert entry.dimension is None
