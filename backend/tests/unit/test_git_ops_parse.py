from __future__ import annotations

from rag.sync.git_ops import _parse_symref_head


def test_parse_symref_head_extracts_main() -> None:
    out = "ref: refs/heads/main\tHEAD\n0123abcdef\tHEAD\n"
    assert _parse_symref_head(out) == "main"


def test_parse_symref_head_extracts_master() -> None:
    out = "ref: refs/heads/master\tHEAD\nabc123\tHEAD\n"
    assert _parse_symref_head(out) == "master"


def test_parse_symref_head_extracts_branch_with_slash() -> None:
    out = "ref: refs/heads/feature/x\tHEAD\nabc\tHEAD\n"
    assert _parse_symref_head(out) == "feature/x"


def test_parse_symref_head_none_when_no_symref() -> None:
    assert _parse_symref_head("0123abc\tHEAD\n") is None


def test_parse_symref_head_none_when_empty() -> None:
    assert _parse_symref_head("") is None
