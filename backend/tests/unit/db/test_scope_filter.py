from __future__ import annotations

import pytest

from rag.db.workspace_search import _ChildHit, _apply_enrichment_filter


def _raw(path: str, idx: int = 0) -> _ChildHit:
    return _ChildHit(
        path=path, chunk_index=idx, chunk_hash=None, section_id=None,
        content="x", score=0.8, metadata=None,
    )


def _enriched(path: str, key: str = "docs", idx: int = 0) -> _ChildHit:
    return _ChildHit(
        path=path, chunk_index=idx, chunk_hash=None, section_id=None,
        content="y", score=0.9,
        metadata={"enrichment_key": key, "source_path": path.split("::")[0]},
    )


class TestApplyEnrichmentFilter:
    def test_scope_both_returns_all(self):
        hits = [_raw("a.py"), _enriched("a.py::docs")]
        result = _apply_enrichment_filter(hits, scope="both", enrichment_keys=None)
        assert len(result) == 2

    def test_scope_raw_only_excludes_enrichments(self):
        hits = [_raw("a.py"), _enriched("a.py::docs")]
        result = _apply_enrichment_filter(hits, scope="raw_only", enrichment_keys=None)
        assert len(result) == 1
        assert result[0].path == "a.py"

    def test_scope_enriched_only_keeps_enrichments(self):
        hits = [_raw("a.py"), _enriched("a.py::docs"), _enriched("a.py::funcs", "public_functions")]
        result = _apply_enrichment_filter(hits, scope="enriched_only", enrichment_keys=None)
        assert len(result) == 2

    def test_enrichment_keys_filter_excludes_other_keys(self):
        hits = [
            _raw("a.py"),
            _enriched("a.py::docs", "documentation"),
            _enriched("a.py::funcs", "public_functions"),
        ]
        result = _apply_enrichment_filter(hits, scope="both", enrichment_keys=["documentation"])
        assert any(h.path == "a.py" for h in result)
        assert any(h.metadata and h.metadata.get("enrichment_key") == "documentation" for h in result)
        assert not any(h.metadata and h.metadata.get("enrichment_key") == "public_functions" for h in result)

    def test_enrichment_keys_none_passes_all_enrichments(self):
        hits = [_raw("a.py"), _enriched("a.py::docs"), _enriched("a.py::funcs", "public_functions")]
        result = _apply_enrichment_filter(hits, scope="both", enrichment_keys=None)
        assert len(result) == 3

    def test_empty_input_returns_empty(self):
        assert _apply_enrichment_filter([], scope="both", enrichment_keys=None) == []
