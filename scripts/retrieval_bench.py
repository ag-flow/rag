#!/usr/bin/env python3
"""Bench de retrieval — hit@5 / MRR@10 sur un golden set (docs/retrieval-measurement.md).

Mesure la qualité de la recherche MCP AVANT/APRÈS activation d'une
configuration (stratégie de chunking, contexte inline…) : même golden set,
mêmes métriques, décision chiffrée.

Usage (depuis la racine du repo) :

    uv run --project backend python scripts/retrieval_bench.py \
        --base-url http://192.168.10.184 \
        --workspace docflow \
        --golden golden/queries.yaml \
        [--api-key … | env RAG_BENCH_API_KEY] [--passes 3] [--top-k 10]

Golden set YAML — une entrée par question, chemins attendus (match sur
`path` OU `source_path` pour couvrir les documents d'enrichissement) :

    - query: "Comment créer un workspace ?"
      expected_paths:
        - manuel/02-workspaces.md
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
from typing import Any

import httpx
import yaml

HIT_AT = 5
DEFAULT_TOP_K = 10
DEFAULT_PASSES = 3  # le reranking peut varier → moyenne sur plusieurs passes


def load_golden(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        entries = yaml.safe_load(fh)
    if not isinstance(entries, list) or not entries:
        sys.exit(f"golden set vide ou invalide : {path}")
    for i, entry in enumerate(entries):
        if not entry.get("query") or not entry.get("expected_paths"):
            sys.exit(f"entrée {i} invalide (query + expected_paths requis)")
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


def first_relevant_rank(hits: list[dict[str, Any]], expected: set[str]) -> int | None:
    """Rang (1-indexé) du premier hit dont path OU source_path est attendu."""
    for rank, hit in enumerate(hits, start=1):
        if hit.get("path") in expected or hit.get("source_path") in expected:
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
) -> tuple[float, float, list[str]]:
    """Une passe complète : (hit@5, MRR@top_k, requêtes en échec)."""
    hits_at_5 = 0
    reciprocal_ranks: list[float] = []
    misses: list[str] = []
    for entry in golden:
        results = search(client, base_url, workspace, api_key, entry["query"], top_k)
        rank = first_relevant_rank(results, set(entry["expected_paths"]))
        if rank is not None and rank <= HIT_AT:
            hits_at_5 += 1
        if rank is None:
            misses.append(entry["query"])
            reciprocal_ranks.append(0.0)
        else:
            reciprocal_ranks.append(1.0 / rank)
    n = len(golden)
    return hits_at_5 / n, sum(reciprocal_ranks) / n, misses


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--golden", required=True)
    parser.add_argument("--api-key", default=os.environ.get("RAG_BENCH_API_KEY"))
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--passes", type=int, default=DEFAULT_PASSES)
    args = parser.parse_args()
    if not args.api_key:
        sys.exit("clé API requise : --api-key ou env RAG_BENCH_API_KEY")

    golden = load_golden(args.golden)
    print(f"Golden set : {len(golden)} question(s) — {args.passes} passe(s), top_k={args.top_k}")

    hit5_scores: list[float] = []
    mrr_scores: list[float] = []
    last_misses: list[str] = []
    with httpx.Client() as client:
        for i in range(args.passes):
            hit5, mrr, misses = run_pass(
                client,
                base_url=args.base_url,
                workspace=args.workspace,
                api_key=args.api_key,
                golden=golden,
                top_k=args.top_k,
            )
            hit5_scores.append(hit5)
            mrr_scores.append(mrr)
            last_misses = misses
            print(f"  passe {i + 1}: hit@{HIT_AT}={hit5:.3f}  MRR@{args.top_k}={mrr:.3f}")

    print(f"\nhit@{HIT_AT}  : {statistics.mean(hit5_scores):.3f}")
    print(f"MRR@{args.top_k} : {statistics.mean(mrr_scores):.3f}")
    if last_misses:
        print(f"\n{len(last_misses)} question(s) sans aucun hit attendu (dernière passe) :")
        for query in last_misses:
            print(f"  - {query}")


if __name__ == "__main__":
    main()
