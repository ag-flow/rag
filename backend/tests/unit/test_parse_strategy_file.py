from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from rag.sync.strategy_config import parse_strategy_file


def test_returns_empty_dict_when_file_absent(tmp_path: Path) -> None:
    result = parse_strategy_file(tmp_path)
    assert result == {}


def test_parses_valid_yaml(tmp_path: Path) -> None:
    rag_dir = tmp_path / ".rag"
    rag_dir.mkdir()
    (rag_dir / "strategy.yml").write_text(
        textwrap.dedent("""\
            strategies:
              LESSONS.md: append
              docs/CHANGELOG.md: append
        """)
    )
    result = parse_strategy_file(tmp_path)
    assert result == {"LESSONS.md": "append", "docs/CHANGELOG.md": "append"}


def test_ignores_unknown_strategy_values(tmp_path: Path) -> None:
    rag_dir = tmp_path / ".rag"
    rag_dir.mkdir()
    (rag_dir / "strategy.yml").write_text(
        textwrap.dedent("""\
            strategies:
              LESSONS.md: append
              README.md: invalid_value
              notes.md: replace
        """)
    )
    result = parse_strategy_file(tmp_path)
    assert "README.md" not in result
    assert result["LESSONS.md"] == "append"
    assert result["notes.md"] == "replace"


def test_returns_empty_dict_when_strategies_key_absent(tmp_path: Path) -> None:
    rag_dir = tmp_path / ".rag"
    rag_dir.mkdir()
    (rag_dir / "strategy.yml").write_text("other_key: value\n")
    result = parse_strategy_file(tmp_path)
    assert result == {}


def test_returns_empty_dict_on_invalid_yaml(tmp_path: Path) -> None:
    rag_dir = tmp_path / ".rag"
    rag_dir.mkdir()
    (rag_dir / "strategy.yml").write_text(":\n  - bad: yaml: content\n")
    result = parse_strategy_file(tmp_path)
    assert result == {}
