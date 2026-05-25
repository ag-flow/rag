from __future__ import annotations

import dataclasses

import pytest

from rag.schemas.mcp import MultiWorkspaceRequest, SingleWorkspaceRequest
from rag.services.mcp import McpWorkspaceRef, normalize_refs


def test_normalize_single_returns_one_ref() -> None:
    req = SingleWorkspaceRequest(workspace="ws_a", api_key="k1", query="q")
    refs = normalize_refs(req)
    assert refs == [McpWorkspaceRef(name="ws_a", api_key="k1")]


def test_normalize_multi_preserves_order_and_size() -> None:
    req = MultiWorkspaceRequest(
        workspaces=[
            {"name": "ws_a", "api_key": "k1"},
            {"name": "ws_b", "api_key": "k2"},
            {"name": "ws_c", "api_key": "k3"},
        ],
        query="q",
    )
    refs = normalize_refs(req)
    assert refs == [
        McpWorkspaceRef(name="ws_a", api_key="k1"),
        McpWorkspaceRef(name="ws_b", api_key="k2"),
        McpWorkspaceRef(name="ws_c", api_key="k3"),
    ]


def test_mcp_workspace_ref_is_frozen() -> None:
    """frozen dataclass empêche un service d'altérer la ref par accident."""
    ref = McpWorkspaceRef(name="ws", api_key="k")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ref.name = "other"  # type: ignore[misc]
