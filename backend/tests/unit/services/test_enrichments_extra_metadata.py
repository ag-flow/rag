from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from rag.services.enrichments import run_enrichments


@pytest.mark.asyncio
async def test_run_enrichments_passes_extra_metadata_to_index_file():
    """run_enrichments injecte {enrichment_key, source_path} dans index_file."""
    ws_id = uuid4()

    trigger_row = {
        "template_id": uuid4(),
        "template_name": "public_functions",
        "metadata_key": "public_functions",
        "result_type": "text",
        "prompt": "List functions in: {content}",
        "llm_provider": "openai",
        "llm_model": "gpt-4o-mini",
        "api_key_ref": None,
        "llm_base_url": None,
    }

    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=None)  # no existing enrichment
    conn.fetch = AsyncMock(return_value=[trigger_row])
    conn.execute = AsyncMock()

    indexer = MagicMock()
    indexer.index_file = AsyncMock(return_value=1)

    with patch("rag.services.enrichments.call_llm", AsyncMock(return_value={"answer": "fn_a, fn_b"})):
        await run_enrichments(
            conn=conn,
            workspace_id=ws_id,
            workspace_name="ws",
            path="src/a.py",
            content="def fn_a(): pass\ndef fn_b(): pass",
            content_hash="sha256:abc",
            indexer=indexer,
            config_pool=None,
            vault_svc=None,
            client_provider=None,
        )

    indexer.index_file.assert_awaited_once()
    call_kwargs = indexer.index_file.call_args.kwargs
    assert "extra_metadata" in call_kwargs
    em = call_kwargs["extra_metadata"]
    assert em["enrichment_key"] == "public_functions"
    assert em["source_path"] == "src/a.py"
