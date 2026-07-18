#!/usr/bin/env python3
"""Bench de retrieval — recall@k / MRR par famille (protocole D9, SR1.2).

Runner de campagne : exécute un jeu de requêtes-vérité contre la recherche
MCP et calcule recall@1/5/10 et MRR, globaux et PAR FAMILLE de questions
(littérale / paraphrasée / indirecte — D9.2). Le verdict est arithmétique :
présence du document source attendu dans le top-k, aucun jugement LLM.
`--report` écrit le rapport markdown à déposer dans le bloc Recherche.

Usage (depuis la racine du repo) :

    uv run --project backend python scripts/retrieval_bench.py \
        --base-url http://192.168.10.184 \
        --workspace docflow \
        --golden golden/queries.yaml \
        [--api-key … | env RAG_BENCH_API_KEY] [--passes 3] [--top-k 10]

Jeu YAML — une entrée par question. `family` ∈ litterale|paraphrasee|
indirecte (optionnel : jeux hors D9). Match : `expected_paths` (exact sur
`path`/`source_path`) et/ou `expected_path_contains` (sous-chaîne — ex. l'id
docflow du document source dans le path poussé) :

    - query: "Comment créer un workspace ?"
      family: paraphrasee
      expected_paths: [manuel/02-workspaces.md]
      expected_path_contains: ["6a398cd2"]
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
from typing import Any

import httpx
import yaml

RECALL_KS = (1, 5, 10)
DEFAULT_TOP_K = 10
DEFAULT_PASSES = 3  # le reranking peut varier → moyenne sur plusieurs passes


def load_golden(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        entries = yaml.safe_load(fh)
    if not isinstance(entries, list) or not entries:
        sys.exit(f"golden set vide ou invalide : {path}")
    for i, entry in enumerate(entries):
        has_expected = entry.get("expected_paths") or entry.get("expected_path_contains")
        if not entry.get("query") or not has_expected:
            sys.exit(f"entrée {i} invalide (query + expected_paths/_contains requis)")
    return entries


def search(
    client: httpx.Client, base_url: str, workspace: str, api_key: str, query: str, top_k: int
) -> list[dict[str, Any]]:
    resp = client.post(
        f"{base_url.rstrip('/')}/mcp",
        json={"workspace": workspace, "api_key": api_key, "query": query, "top_k": top_k},
        timeout=60.0,
    )
    resp.raise_for_status()
    return list(resp.json()["results"])


def first_relevant_rank(hits: list[dict[str, Any]], entry: dict[str, Any]) -> int | None:
    """Rang (1-indexé) du premier hit provenant du document attendu."""
    exact = set(entry.get("expected_paths") or [])
    fragments = list(entry.get("expected_path_contains") or [])
    for rank, hit in enumerate(hits, start=1):
        paths = [p for p in (hit.get("path"), hit.get("source_path")) if p]
        if any(p in exact for p in paths):
            return rank
        if any(frag in p for frag in fragments for p in paths):
            return rank
    return None


def run_pass(
    client: httpx.Client,
    *,
    base_url: str,
    workspace: str,
    api_key: str,
    golden: list[dict[str, Any]],
    top_k: int,
) -> list[int | None]:
    """Une passe complète : rang du doc attendu par question (None = absent)."""
    return [
        first_relevant_rank(
            search(client, base_url, workspace, api_key, entry["query"], top_k), entry
        )
        for entry in golden
    ]


def metrics(ranks: list[int | None]) -> dict[str, float]:
    """recall@k (k ∈ RECALL_KS) et MRR — verdict arithmétique (D9.1)."""
    n = len(ranks) or 1
    out = {f"recall@{k}": sum(1 for r in ranks if r is not None and r <= k) / n for k in RECALL_KS}
    out["mrr"] = sum(1.0 / r for r in ranks if r is not None) / n
    return out


def render_report(
    golden: list[dict[str, Any]],
    all_ranks: list[list[int | None]],
    *,
    workspace: str,
    top_k: int,
) -> str:
    """Rapport markdown à déposer dans le bloc Recherche (SR1.2)."""

    def avg(rows: list[dict[str, float]]) -> dict[str, float]:
        keys = rows[0].keys()
        return {k: statistics.mean(r[k] for r in rows) for k in keys}

    lines = [
        "# Rapport de campagne de recherche",
        "",
        f"- Workspace : `{workspace}` — top_k={top_k}, passes={len(all_ranks)}",
        f"- Jeu : {len(golden)} question(s)",
        "",
        "## Métriques globales",
        "",
    ]
    overall = avg([metrics(ranks) for ranks in all_ranks])
    lines += [f"- **{k}** : {v:.3f}" for k, v in overall.items()]
    families = sorted({e.get("family", "sans-famille") for e in golden})
    if len(families) > 1:
        lines += ["", "## Par famille", ""]
        for family in families:
            idx = [i for i, e in enumerate(golden) if e.get("family", "sans-famille") == family]
            fam = avg([metrics([ranks[i] for i in idx]) for ranks in all_ranks])
            fam_str = "  ".join(f"{k}={v:.3f}" for k, v in fam.items())
            lines.append(f"- **{family}** ({len(idx)} q) : {fam_str}")
    last = all_ranks[-1]
    misses = [golden[i]["query"] for i, r in enumerate(last) if r is None]
    if misses:
        lines += ["", f"## Échecs (dernière passe : {len(misses)})", ""]
        lines += [f"- {q}" for q in misses]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--golden", required=True)
    parser.add_argument("--api-key", default=os.environ.get("RAG_BENCH_API_KEY"))
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--passes", type=int, default=DEFAULT_PASSES)
    parser.add_argument("--report", help="chemin du rapport markdown (bloc Recherche)")
    args = parser.parse_args()
    if not args.api_key:
        sys.exit("clé API requise : --api-key ou env RAG_BENCH_API_KEY")

    golden = load_golden(args.golden)
    print(f"Jeu : {len(golden)} question(s) — {args.passes} passe(s), top_k={args.top_k}")

    all_ranks: list[list[int | None]] = []
    with httpx.Client() as client:
        for i in range(args.passes):
            ranks = run_pass(
                client,
                base_url=args.base_url,
                workspace=args.workspace,
                api_key=args.api_key,
                golden=golden,
                top_k=args.top_k,
            )
            all_ranks.append(ranks)
            pass_metrics = metrics(ranks)
            summary = "  ".join(f"{k}={v:.3f}" for k, v in pass_metrics.items())
            print(f"  passe {i + 1}: {summary}")

    report = render_report(golden, all_ranks, workspace=args.workspace, top_k=args.top_k)
    print("\n" + report)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"Rapport écrit : {args.report}")


if __name__ == "__main__":
    main()
