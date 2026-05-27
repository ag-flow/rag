"""Tests unitaires pour ChunkingChangeRequiresReindex (errors.py).

Mirror de IndexerChangeRequiresReindex (cf. errors.py:85). Différence : le
payload chunking porte `new` (et non `requested`) + une `action` PUT, comme
défini dans le design M9 §5.2.
"""

from __future__ import annotations

from rag.api.errors import AdminError, ChunkingChangeRequiresReindex


def test_error_payload_format() -> None:
    err = ChunkingChangeRequiresReindex(
        workspace="ws_x",
        current="paragraph (max=2000, min=200, overlap=200)",
        new="paragraph (max=1500, min=100, overlap=150)",
    )
    payload = err.to_payload()
    assert payload["error"] == "chunking_change_requires_reindex"
    assert payload["workspace"] == "ws_x"
    assert payload["current"] == "paragraph (max=2000, min=200, overlap=200)"
    assert payload["new"] == "paragraph (max=1500, min=100, overlap=150)"
    assert payload["action"] == "PUT /workspaces/ws_x/chunking-config?confirm=true"


def test_error_http_status_409() -> None:
    err = ChunkingChangeRequiresReindex(
        workspace="ws",
        current="a",
        new="b",
    )
    assert err.http_status == 409


def test_error_is_admin_error_subclass() -> None:
    err = ChunkingChangeRequiresReindex(workspace="ws", current="a", new="b")
    assert isinstance(err, AdminError)


def test_error_attributes_exposed() -> None:
    """Les kwargs sont accessibles en attributs (parité avec sibling)."""
    err = ChunkingChangeRequiresReindex(
        workspace="ws1",
        current="paragraph (max=2000, min=200, overlap=200)",
        new="paragraph (max=800, min=80, overlap=80)",
    )
    assert err.workspace == "ws1"
    assert err.current == "paragraph (max=2000, min=200, overlap=200)"
    assert err.new == "paragraph (max=800, min=80, overlap=80)"
