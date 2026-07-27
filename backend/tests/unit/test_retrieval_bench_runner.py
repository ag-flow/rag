"""Runner de campagne (SR1.2) : chargement du jeu versionné et rapport.

Le runner vit dans scripts/ ; on le charge par chemin pour tester load_golden
(format liste hérité + format versionné du bloc Recherche) et render_report
(version du jeu, configuration testée, échecs détaillés par famille).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_BENCH = Path(__file__).resolve().parents[2].parent / "scripts" / "retrieval_bench.py"
_spec = importlib.util.spec_from_file_location("retrieval_bench_runner", _BENCH)
assert _spec and _spec.loader
bench = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = bench  # requis par @dataclass (résolution via sys.modules)
_spec.loader.exec_module(bench)

_LEGACY_YAML = """\
- query: "Comment créer un workspace ?"
  family: paraphrasee
  expected_paths: [manuel/02-workspaces.md]
"""

_VERSIONED_YAML = """\
version: v0
generated_by: agent-generateur-D9
generated_at: "2026-07-18"
queries:
  - query: "Quelle est la valeur par défaut du top_k pre-rerank ?"
    family: litterale
    expected_path_contains: ["7a753653"]
  - query: "Il y a un parcours guidé ?"
    family: indirecte
    expected_path_contains: ["7a753653"]
"""


class TestLoadGolden:
    def test_legacy_list_format(self, tmp_path: Path) -> None:
        path = tmp_path / "legacy.yaml"
        path.write_text(_LEGACY_YAML, encoding="utf-8")
        golden = bench.load_golden(str(path))
        assert golden.version is None
        assert len(golden.queries) == 1
        assert golden.queries[0]["family"] == "paraphrasee"

    def test_versioned_format(self, tmp_path: Path) -> None:
        path = tmp_path / "jeu.yaml"
        path.write_text(_VERSIONED_YAML, encoding="utf-8")
        golden = bench.load_golden(str(path))
        assert golden.version == "v0"
        assert len(golden.queries) == 2

    def test_versioned_without_queries_exits(self, tmp_path: Path) -> None:
        path = tmp_path / "vide.yaml"
        path.write_text("version: v1\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            bench.load_golden(str(path))

    def test_invalid_entry_exits(self, tmp_path: Path) -> None:
        path = tmp_path / "invalide.yaml"
        path.write_text("version: v1\nqueries:\n  - query: sans-attendu\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            bench.load_golden(str(path))


def _golden() -> object:
    return bench.GoldenSet(
        version="v0",
        queries=[
            {"query": "q-lit", "family": "litterale", "expected_path_contains": ["aaa"]},
            {"query": "q-ind", "family": "indirecte", "expected_path_contains": ["bbb"]},
        ],
    )


class TestRenderReport:
    def test_includes_version_and_config(self) -> None:
        report = bench.render_report(
            _golden(),
            [[1, None]],
            workspace="ws",
            top_k=10,
            config_note="vectoriel seul (baseline)",
        )
        assert "v0" in report
        assert "vectoriel seul (baseline)" in report

    def test_config_note_defaults_to_unspecified(self) -> None:
        report = bench.render_report(_golden(), [[1, 2]], workspace="ws", top_k=10)
        assert "non renseignée" in report

    def test_failures_carry_family_and_expected(self) -> None:
        report = bench.render_report(_golden(), [[1, None]], workspace="ws", top_k=10)
        assert "q-ind" in report
        assert "indirecte" in report
        assert "bbb" in report
        assert "absent du top-10" in report

    def test_per_family_metrics(self) -> None:
        report = bench.render_report(_golden(), [[1, None]], workspace="ws", top_k=10)
        assert "litterale" in report
        assert "recall@1=1.000" in report
