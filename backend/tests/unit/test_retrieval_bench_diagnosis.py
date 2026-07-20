"""Classification déterministe des échecs de campagne (SR1.3), sans infra ni LLM.

Le runner vit dans scripts/ ; on le charge par chemin pour tester classify_failure
et render_diagnosis sur des payloads synthétiques (canaux D8).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_BENCH = Path(__file__).resolve().parents[2].parent / "scripts" / "retrieval_bench.py"
_spec = importlib.util.spec_from_file_location("retrieval_bench", _BENCH)
assert _spec and _spec.loader
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)


def _hit(path: str, rank: int) -> dict:
    return {"path": path, "chunk_index": 0, "rank": rank, "score": 1.0 / rank}


def _payload(vector: list[dict], lexical: list[dict], results: list[dict] | None = None) -> dict:
    return {"results": results or [], "channels": {"vector": vector, "lexical": lexical}}


_ENTRY = {"query": "q", "expected_paths": ["doc.md"]}


class TestClassifyFailure:
    def test_absent_both(self) -> None:
        diag = bench.classify_failure(_ENTRY, _payload([_hit("autre.md", 1)], [_hit("x.md", 1)]))
        assert diag["verdict"] == "absent_both"
        assert diag["vector_rank"] is None and diag["lexical_rank"] is None

    def test_vector_only(self) -> None:
        diag = bench.classify_failure(_ENTRY, _payload([_hit("doc.md", 3)], [_hit("x.md", 1)]))
        assert diag["verdict"] == "vector_only"
        assert diag["vector_rank"] == 3

    def test_lexical_only(self) -> None:
        diag = bench.classify_failure(_ENTRY, _payload([_hit("x.md", 1)], [_hit("doc.md", 2)]))
        assert diag["verdict"] == "lexical_only"
        assert diag["lexical_rank"] == 2

    def test_drowned_fusion(self) -> None:
        diag = bench.classify_failure(_ENTRY, _payload([_hit("doc.md", 4)], [_hit("doc.md", 5)]))
        assert diag["verdict"] == "drowned_fusion"
        assert diag["vector_rank"] == 4 and diag["lexical_rank"] == 5

    def test_baseline_vector_low_rank_when_no_lexical(self) -> None:
        # Canal lexical vide (baseline vectoriel-seul) → verdict spécifique.
        diag = bench.classify_failure(_ENTRY, _payload([_hit("doc.md", 12)], []))
        assert diag["verdict"] == "vector_low_rank"
        assert diag["vector_rank"] == 12

    def test_expected_path_contains_fragment(self) -> None:
        entry = {"query": "q", "expected_path_contains": ["6a398cd2"]}
        diag = bench.classify_failure(entry, _payload([_hit("push/6a398cd2-x.md", 2)], []))
        assert diag["verdict"] == "vector_low_rank"
        assert diag["vector_rank"] == 2


class TestRenderDiagnosis:
    def test_report_includes_verdict_and_hypotheses(self) -> None:
        failures = [(_ENTRY, _payload([_hit("doc.md", 4)], [_hit("doc.md", 5)], results=[]))]
        report = bench.render_diagnosis(failures, workspace="ws", top_k=3)
        assert "verdict" in report
        assert "noyé à la fusion" in report
        assert "hypothèses proposées" in report
