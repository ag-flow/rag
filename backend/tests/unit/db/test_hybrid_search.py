from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.db.workspace_search import _ChildHit, hybrid_search, lexical_search, rrf_fuse


def _ch(
    path: str,
    idx: int,
    hash_: str | None = None,
    sec: int | None = None,
    score: float = 0.9,
) -> _ChildHit:
    return _ChildHit(
        path=path,
        chunk_index=idx,
        chunk_hash=hash_,
        section_id=sec,
        content=f"content of {path}:{idx}",
        score=score,
    )


class TestRrfFuse:
    def test_chunk_only_in_vector_gets_one_contribution(self):
        v = [_ch("a.py", 0, "h1")]
        result = rrf_fuse(v, [], k=60)
        assert len(result) == 1
        r = result[0]
        assert r.vector_rank == 1
        assert r.lexical_rank is None
        assert abs(r.rrf_score - 0.5 / (60 + 1)) < 1e-9

    def test_chunk_only_in_lexical_gets_one_contribution(self):
        lex = [_ch("b.py", 0, "h2")]
        result = rrf_fuse([], lex, k=60)
        assert len(result) == 1
        r = result[0]
        assert r.lexical_rank == 1
        assert r.vector_rank is None
        assert abs(r.rrf_score - 0.5 / (60 + 1)) < 1e-9

    def test_chunk_in_both_bras_cumulates(self):
        v = [_ch("c.py", 0, "h3"), _ch("d.py", 1, "h4")]
        lex = [_ch("c.py", 0, "h3"), _ch("e.py", 2, "h5")]
        result = rrf_fuse(v, lex, k=60)
        shared = next(r for r in result if r.path == "c.py")
        solo_v = next(r for r in result if r.path == "d.py")
        solo_l = next(r for r in result if r.path == "e.py")
        assert shared.rrf_score > solo_v.rrf_score
        assert shared.rrf_score > solo_l.rrf_score
        assert shared.vector_rank == 1
        assert shared.lexical_rank == 1

    def test_result_sorted_by_rrf_score_desc(self):
        v = [_ch("c.py", 0, "h1"), _ch("a.py", 0, "h2")]
        lex = [_ch("c.py", 0, "h1"), _ch("b.py", 0, "h3")]
        result = rrf_fuse(v, lex)
        assert result[0].path == "c.py"
        scores = [r.rrf_score for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_legacy_identity_uses_chunk_index(self):
        v = [_ch("a.py", 5, None)]
        lex = [_ch("a.py", 5, None)]
        result = rrf_fuse(v, lex)
        assert len(result) == 1
        assert result[0].vector_rank == 1
        assert result[0].lexical_rank == 1

    def test_legacy_different_chunk_index_two_results(self):
        v = [_ch("a.py", 0, None)]
        lex = [_ch("a.py", 1, None)]
        result = rrf_fuse(v, lex)
        assert len(result) == 2

    def test_empty_inputs_returns_empty(self):
        assert rrf_fuse([], []) == []

    def test_k_parameter_affects_score(self):
        v = [_ch("a.py", 0, "h1")]
        r60 = rrf_fuse(v, [], k=60)[0]
        r10 = rrf_fuse(v, [], k=10)[0]
        assert r10.rrf_score > r60.rrf_score


def _make_pool_lex(rows: list[dict]) -> MagicMock:
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


class TestLexicalSearch:
    @pytest.mark.asyncio
    async def test_returns_child_hits_ordered_by_ts_rank(self):
        rows = [
            {
                "path": "a.py",
                "chunk_index": 0,
                "chunk_hash": "h1",
                "section_id": None,
                "content": "hello world",
                "lexical_score": 0.8,
                "metadata": None,
            },
            {
                "path": "b.py",
                "chunk_index": 1,
                "chunk_hash": "h2",
                "section_id": 5,
                "content": "parent text",
                "lexical_score": 0.5,
                "metadata": None,
            },
        ]
        pool = _make_pool_lex(rows)
        hits = await lexical_search(pool, query="hello", top_k_fetch=10)
        assert len(hits) == 2
        assert hits[0].path == "a.py"
        assert hits[0].score == pytest.approx(0.8)
        assert hits[0].chunk_hash == "h1"
        assert hits[0].section_id is None
        assert hits[1].section_id == 5

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_list(self):
        pool = _make_pool_lex([])
        hits = await lexical_search(pool, query="notfound", top_k_fetch=5)
        assert hits == []

    @pytest.mark.asyncio
    async def test_passes_top_k_fetch_as_limit(self):
        pool = _make_pool_lex([])
        await lexical_search(pool, query="x", top_k_fetch=42)
        conn = pool.acquire.return_value.__aenter__.return_value
        args = conn.fetch.call_args[0]
        assert args[-1] == 42


class _StubEngine:
    """Moteur lexical factice : renvoie la liste fournie (contrat D5)."""

    slug = "stub"

    def __init__(self, hits):
        self._hits = hits

    async def search(self, pool, *, query, top_k_fetch):
        return self._hits


class TestHybridSearch:
    @pytest.mark.asyncio
    async def test_chunk_in_both_bras_ranked_first(self, monkeypatch):
        """Chunk présent dans les deux bras remonte en tête via RRF."""
        from rag.db import workspace_search as ws_mod
        from rag.db.workspace_search import _ChildHit

        async def fake_vec(p, *, query_vec, top_k_fetch, min_score):
            return [
                _ChildHit("shared.py", 0, "h_shared", None, "shared content", 0.7),
                _ChildHit("only_v.py", 0, "h_v", None, "vector only", 0.95),
            ]

        engine = _StubEngine(
            [
                _ChildHit("shared.py", 0, "h_shared", None, "shared content", 0.6),
            ]
        )

        monkeypatch.setattr(ws_mod, "_fetch_vector_children", fake_vec)

        pool = MagicMock()
        result = await hybrid_search(
            pool,
            query_vec=[0.1],
            query="shared",
            top_k=5,
            min_score=0.0,
            workspace_name="ws",
            indexer_used="openai/m",
            lexical_engine=engine,
        )
        assert result.hits[0].path == "shared.py"
        # canaux bruts exposés pour le flag debug (D8)
        assert [c.path for c in result.lexical_channel] == ["shared.py"]
        assert len(result.vector_channel) == 2

    @pytest.mark.asyncio
    async def test_section_dedup_after_rrf(self, monkeypatch):
        """Deux enfants d'une même section → un seul hit."""
        from rag.db import workspace_search as ws_mod
        from rag.db.workspace_search import _ChildHit

        async def fake_vec(p, **kw):
            return [
                _ChildHit("f.py", 0, "h1", section_id=10, content="parent A", score=0.9),
                _ChildHit("f.py", 1, "h2", section_id=10, content="parent A", score=0.8),
            ]

        monkeypatch.setattr(ws_mod, "_fetch_vector_children", fake_vec)

        pool = MagicMock()
        result = await hybrid_search(
            pool,
            query_vec=[0.1],
            query="x",
            top_k=10,
            min_score=0.0,
            workspace_name="ws",
            indexer_used="openai/m",
            lexical_engine=_StubEngine([]),
        )
        assert len(result.hits) == 1

    @pytest.mark.asyncio
    async def test_provenance_always_present(self, monkeypatch):
        """D8 : chaque résultat expose sa provenance, même sans flag debug."""
        from rag.db import workspace_search as ws_mod
        from rag.db.workspace_search import _ChildHit

        async def fake_vec(p, **kw):
            return [_ChildHit("a.py", 0, "h1", None, "c", 0.9)]

        monkeypatch.setattr(ws_mod, "_fetch_vector_children", fake_vec)

        pool = MagicMock()
        result = await hybrid_search(
            pool,
            query_vec=[0.1],
            query="x",
            top_k=5,
            min_score=0.0,
            workspace_name="ws",
            indexer_used="openai/m",
            lexical_engine=_StubEngine([]),
        )
        assert all(h.debug is not None for h in result.hits)
        assert result.hits[0].debug.vector_rank == 1

    @pytest.mark.asyncio
    async def test_debug_true_populates_trace(self, monkeypatch):
        from rag.db import workspace_search as ws_mod
        from rag.db.workspace_search import _ChildHit

        async def fake_vec(p, **kw):
            return [_ChildHit("a.py", 0, "h1", None, "c", 0.9)]

        monkeypatch.setattr(ws_mod, "_fetch_vector_children", fake_vec)

        pool = MagicMock()
        result = await hybrid_search(
            pool,
            query_vec=[0.1],
            query="x",
            top_k=5,
            min_score=0.0,
            workspace_name="ws",
            indexer_used="openai/m",
            lexical_engine=_StubEngine([_ChildHit("a.py", 0, "h1", None, "c", 0.7)]),
        )
        hits = result.hits
        assert len(hits) == 1
        d = hits[0].debug
        assert d is not None
        assert d.vector_rank == 1
        assert d.lexical_rank == 1
        assert d.rrf_score is not None
        assert d.final_rank == 1


class TestWeightedRrf:
    def test_weights_shift_the_ranking(self):
        """D6 : à rangs égaux, le canal le plus pondéré gagne."""
        v = [_ChildHit("vec.md", 0, "hv", None, "v", 0.9)]
        lex = [_ChildHit("lex.md", 0, "hl", None, "l", 0.8)]
        lex_first = rrf_fuse(v, lex, k=60, w_vector=0.2, w_lexical=0.8)
        assert lex_first[0].path == "lex.md"
        vec_first = rrf_fuse(v, lex, k=60, w_vector=0.8, w_lexical=0.2)
        assert vec_first[0].path == "vec.md"

    def test_zero_weight_silences_a_channel(self):
        v = [_ChildHit("vec.md", 0, "hv", None, "v", 0.9)]
        lex = [_ChildHit("lex.md", 0, "hl", None, "l", 0.8)]
        fused = rrf_fuse(v, lex, k=60, w_vector=1.0, w_lexical=0.0)
        by_path = {f.path: f.rrf_score for f in fused}
        assert by_path["lex.md"] == 0.0
        assert by_path["vec.md"] > 0.0
