#!/usr/bin/env python3
"""Génère le diff de chunks legacy vs structured d'un fichier, pour inspection
humaine avant bascule d'un workspace (ADR 0001, Lot 1).

Usage :
    python scripts/chunk_diff.py <fichier.md> [--algo prose|table] [--max-tokens 8192]

Sortie : rapport texte sur stdout (rediriger vers un fichier au besoin).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rag.indexer.chunking.diff_report import render_chunk_diff


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diff de chunks legacy vs structured")
    parser.add_argument("file", type=Path, help="Fichier à découper")
    parser.add_argument("--algo", default="prose", choices=["prose", "markdown", "table"])
    parser.add_argument("--max-tokens", type=int, default=8192, dest="max_tokens")
    parser.add_argument("--char-ratio", type=float, default=4.0, dest="char_ratio")
    args = parser.parse_args(argv)

    content = args.file.read_text(encoding="utf-8")
    report = render_chunk_diff(
        content,
        structured_algo=args.algo,
        char_ratio=args.char_ratio,
        provider_max_input_tokens=args.max_tokens,
    )
    sys.stdout.write(report + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
