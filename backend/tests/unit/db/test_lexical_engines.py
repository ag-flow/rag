from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.db.lexical_engines import Bm25Engine, FtsEngine, get_lexical_engine


class TestRegistry:
    def test_known_engines(self) -> None:
        assert get_lexical_engine("fts").slug == "fts"
        assert get_lexical_engine("bm25").slug == "bm25"

    def test_unknown_engine_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown lexical engine"):
            get_lexical_engine("elastic")


@pytest.mark.asyncio
async def test_fts_always_available() -> None:
    assert await FtsEngine().is_available(MagicMock()) is True


@pytest.mark.asyncio
async def test_bm25_availability_reads_pg_available_extensions() -> None:
    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value=None)
    assert await Bm25Engine().is_available(conn) is False
    assert "pg_available_extensions" in conn.fetchval.call_args[0][0]
    conn.fetchval = AsyncMock(return_value=1)
    assert await Bm25Engine().is_available(conn) is True


@pytest.mark.asyncio
async def test_ensure_index_swaps_indexes() -> None:
    """La bascule retire l'index de l'autre moteur (D5 : reconstruction)."""
    conn = MagicMock()
    conn.execute = AsyncMock()
    await FtsEngine().ensure_index(conn)
    executed = " ".join(str(c.args[0]) for c in conn.execute.call_args_list)
    assert "DROP INDEX IF EXISTS embeddings_bm25" in executed
    assert "USING GIN (content_tsv)" in executed

    conn2 = MagicMock()
    conn2.execute = AsyncMock()
    await Bm25Engine().ensure_index(conn2)
    executed2 = " ".join(str(c.args[0]) for c in conn2.execute.call_args_list)
    assert "CREATE EXTENSION IF NOT EXISTS pg_search" in executed2
    assert "DROP INDEX IF EXISTS embeddings_content_tsv" in executed2
    assert "USING bm25" in executed2


@pytest.mark.asyncio
async def test_bm25_search_maps_rows() -> None:
    row: dict[str, Any] = {
        "path": "a.md",
        "chunk_index": 0,
        "chunk_hash": "h",
        "section_id": None,
        "content": "c",
        "lexical_score": 4.2,
        "metadata": None,
    }
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[row])
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    hits = await Bm25Engine().search(pool, query="x", top_k_fetch=10)
    assert hits[0].path == "a.md" and hits[0].score == 4.2
    assert "@@@" in conn.fetch.call_args[0][0]
