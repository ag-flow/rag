from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from rag.schemas.mcp import (
    McpRequest,
    MultiWorkspaceRequest,
    SearchHit,
    SingleWorkspaceRequest,
)

_ADAPTER = TypeAdapter(McpRequest)


def test_single_request_accepts_minimal_payload() -> None:
    req = SingleWorkspaceRequest(
        workspace="harpocrate",
        api_key="ws_key_xyz",
        query="comment ça marche ?",
    )
    assert req.workspace == "harpocrate"
    assert req.top_k == 5  # default
    assert req.min_score == 0.7  # default


def test_multi_request_accepts_workspaces_list() -> None:
    req = MultiWorkspaceRequest(
        workspaces=[
            {"name": "ws_a", "api_key": "k1"},
            {"name": "ws_b", "api_key": "k2"},
        ],
        query="hello",
    )
    assert len(req.workspaces) == 2
    assert req.workspaces[0].name == "ws_a"


def test_union_dispatches_single_when_workspace_field_present() -> None:
    obj = _ADAPTER.validate_python(
        {
            "workspace": "ws",
            "api_key": "k",
            "query": "q",
        }
    )
    assert isinstance(obj, SingleWorkspaceRequest)


def test_union_dispatches_multi_when_workspaces_field_present() -> None:
    obj = _ADAPTER.validate_python(
        {
            "workspaces": [{"name": "ws", "api_key": "k"}],
            "query": "q",
        }
    )
    assert isinstance(obj, MultiWorkspaceRequest)


def test_union_rejects_mix_of_single_and_multi() -> None:
    with pytest.raises(ValidationError):
        _ADAPTER.validate_python(
            {
                "workspace": "ws",
                "api_key": "k",
                "workspaces": [{"name": "ws", "api_key": "k"}],
                "query": "q",
            }
        )


def test_single_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        SingleWorkspaceRequest(workspace="ws", api_key="k", query="")


def test_single_rejects_query_above_2000_chars() -> None:
    with pytest.raises(ValidationError):
        SingleWorkspaceRequest(
            workspace="ws",
            api_key="k",
            query="a" * 2001,
        )


def test_single_rejects_top_k_zero() -> None:
    with pytest.raises(ValidationError):
        SingleWorkspaceRequest(workspace="ws", api_key="k", query="q", top_k=0)


def test_single_rejects_top_k_above_50() -> None:
    with pytest.raises(ValidationError):
        SingleWorkspaceRequest(workspace="ws", api_key="k", query="q", top_k=51)


def test_single_rejects_min_score_above_one() -> None:
    with pytest.raises(ValidationError):
        SingleWorkspaceRequest(
            workspace="ws",
            api_key="k",
            query="q",
            min_score=1.1,
        )


def test_single_rejects_min_score_below_minus_one() -> None:
    with pytest.raises(ValidationError):
        SingleWorkspaceRequest(
            workspace="ws",
            api_key="k",
            query="q",
            min_score=-1.1,
        )


def test_multi_rejects_empty_workspaces_list() -> None:
    with pytest.raises(ValidationError):
        MultiWorkspaceRequest(workspaces=[], query="q")


def test_multi_rejects_more_than_10_workspaces() -> None:
    with pytest.raises(ValidationError):
        MultiWorkspaceRequest(
            workspaces=[{"name": f"ws_{i}", "api_key": "k"} for i in range(11)],
            query="q",
        )


def test_single_rejects_invalid_workspace_name() -> None:
    with pytest.raises(ValidationError):
        SingleWorkspaceRequest(
            workspace="Invalid Name",  # uppercase + space
            api_key="k",
            query="q",
        )


def test_search_hit_serializes_full_payload() -> None:
    hit = SearchHit(
        workspace="ws",
        indexer="openai/text-embedding-3-small",
        path="docs/foo.md",
        chunk_index=2,
        content="extrait",
        score=0.91,
    )
    d = hit.model_dump()
    assert d["workspace"] == "ws"
    assert d["indexer"] == "openai/text-embedding-3-small"
    assert d["score"] == 0.91
