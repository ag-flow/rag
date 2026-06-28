from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.indexer.noop import NoOpIndexer


class TestExtraMetadataSignature:
    @pytest.mark.asyncio
    async def test_noop_accepts_extra_metadata_none(self):
        """index_file avec extra_metadata=None → comportement inchangé."""
        pool = MagicMock()
        conn = MagicMock()
        conn.execute = AsyncMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        pool.acquire = MagicMock(return_value=conn)

        indexer = NoOpIndexer(pool)
        n = await indexer.index_file(
            workspace_id=uuid4(),
            path="src/a.py",
            content="x",
            content_hash="sha256:abc",
            indexer_used="openai/m",
            extra_metadata=None,
        )
        assert n == 1

    @pytest.mark.asyncio
    async def test_noop_accepts_extra_metadata_dict(self):
        pool = MagicMock()
        conn = MagicMock()
        conn.execute = AsyncMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        pool.acquire = MagicMock(return_value=conn)

        indexer = NoOpIndexer(pool)
        n = await indexer.index_file(
            workspace_id=uuid4(),
            path="src/b.py",
            content="x",
            content_hash="sha256:abc",
            indexer_used="openai/m",
            extra_metadata={"enrichment_key": "public_functions", "source_path": "src/b.py"},
        )
        assert n == 1


class TestExtraMetadataMergeLogic:
    """Vérifie la logique de merge — chunker keys gagnent."""

    def test_chunker_keys_win_over_extra_metadata(self):
        from rag.indexer.chunking.protocol import Chunk

        chunk = Chunk(content="hello", metadata={"scope": "MyClass.my_method", "heading_level": 2})
        extra = {"scope": "INJECTED", "enrichment_key": "docs"}
        # merge : extra first, chunker metadata second (chunker gagne)
        merged = {**extra, **dict(chunk.metadata)}
        assert merged["scope"] == "MyClass.my_method"    # chunker gagne
        assert merged["heading_level"] == 2               # chunker préservé
        assert merged["enrichment_key"] == "docs"         # extra injecté

    def test_extra_metadata_fills_absent_keys(self):
        from rag.indexer.chunking.protocol import Chunk

        chunk = Chunk(content="x", metadata={"scope": "fn"})
        extra = {"enrichment_key": "public_functions", "source_path": "a.py"}
        merged = {**extra, **dict(chunk.metadata)}
        assert merged["enrichment_key"] == "public_functions"
        assert merged["source_path"] == "a.py"
        assert merged["scope"] == "fn"
