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

Jeu YAML — deux formats acceptés : la liste brute d'entrées, ou le format
versionné du bloc Recherche (en-tête `version:` + `queries:` — D9.3, le
rapport référence alors la version). `family` ∈ litterale|paraphrasee|
indirecte (optionnel : jeux hors D9). Match : `expected_paths` (exact sur
`path`/`source_path`) et/ou `expected_path_contains` (sous-chaîne — ex. l'id
docflow du document source dans le path poussé) :

    version: v1
    queries:
      - query: "Comment créer un workspace ?"
        family: paraphrasee
        expected_paths: [manuel/02-workspaces.md]
        expected_path_contains: ["6a398cd2"]

`--config-note` décrit la configuration testée (moteur, curseurs, contexte
F6 actif ou non) et est reprise telle quelle dans le rapport.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
from dataclasses import dataclass
from typing import Any

import httpx
import yaml

RECALL_KS = (1, 5, 10)
DEFAULT_TOP_K = 10
DEFAULT_PASSES = 3  # le reranking peut varier → moyenne sur plusieurs passes


@dataclass(frozen=True)
class GoldenSet:
    """Jeu de requêtes-vérité chargé : entrées + version (None = jeu non versionné)."""

    version: str | None
    queries: list[dict[str, Any]]


def load_golden(path: str) -> GoldenSet:
    """Charge le jeu : liste brute, ou format versionné du bloc Recherche (D9.3)."""
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    version: str | None = None
    if isinstance(raw, dict):
        version = str(raw["version"]) if raw.get("version") is not None else None
        raw = raw.get("queries")
    if not isinstance(raw, list) or not raw:
        sys.exit(f"golden set vide ou invalide : {path}")
    for i, entry in enumerate(raw):
        has_expected = entry.get("expected_paths") or entry.get("expected_path_contains")
        if not entry.get("query") or not has_expected:
            sys.exit(f"entrée {i} invalide (query + expected_paths/_contains requis)")
    return GoldenSet(version=version, queries=raw)


def search(
    client: httpx.Client, base_url: str, workspace: str, api_key: str, query: str, top_k: int
) -> list[dict[str, Any]]:
    resp = client.post(
        f"{base_url.rstrip('/')}/api/v1/search",
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
    golden: GoldenSet,
    all_ranks: list[list[int | None]],
    *,
    workspace: str,
    top_k: int,
    config_note: str | None = None,
) -> str:
    """Rapport markdown à déposer dans le bloc Recherche (SR1.2) : version du
    jeu, configuration testée, métriques globales et par famille, échecs."""

    def avg(rows: list[dict[str, float]]) -> dict[str, float]:
        keys = rows[0].keys()
        return {k: statistics.mean(r[k] for r in rows) for k in keys}

    queries = golden.queries
    lines = [
        "# Rapport de campagne de recherche",
        "",
        f"- Workspace : `{workspace}` — top_k={top_k}, passes={len(all_ranks)}",
        f"- Jeu : {golden.version or 'non versionné'} — {len(queries)} question(s)",
        f"- Configuration testée : {config_note or 'non renseignée'}",
        "",
        "## Métriques globales",
        "",
    ]
    overall = avg([metrics(ranks) for ranks in all_ranks])
    lines += [f"- **{k}** : {v:.3f}" for k, v in overall.items()]
    families = sorted({e.get("family", "sans-famille") for e in queries})
    if len(families) > 1:
        lines += ["", "## Par famille", ""]
        for family in families:
            idx = [i for i, e in enumerate(queries) if e.get("family", "sans-famille") == family]
            fam = avg([metrics([ranks[i] for i in idx]) for ranks in all_ranks])
            fam_str = "  ".join(f"{k}={v:.3f}" for k, v in fam.items())
            lines.append(f"- **{family}** ({len(idx)} q) : {fam_str}")
    last = all_ranks[-1]
    misses = [i for i, r in enumerate(last) if r is None]
    if misses:
        lines += ["", f"## Échecs (dernière passe : {len(misses)})", ""]
        for i in misses:
            entry = queries[i]
            expected = entry.get("expected_paths") or entry.get("expected_path_contains")
            lines.append(
                f"- {entry['query']} — famille : {entry.get('family', 'sans-famille')}, "
                f"attendu : {expected}, absent du top-{top_k}"
            )
    return "\n".join(lines) + "\n"


def search_debug(
    client: httpx.Client, base_url: str, workspace: str, api_key: str, query: str, top_k: int
) -> dict[str, Any]:
    """Réponse COMPLÈTE de /api/v1/search avec debug=true (results + channels, D8)."""
    resp = client.post(
        f"{base_url.rstrip('/')}/api/v1/search",
        json={
            "workspace": workspace,
            "api_key": api_key,
            "query": query,
            "top_k": top_k,
            "debug": True,
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    return dict(resp.json())


def _expected_matcher(entry: dict[str, Any]):
    """Prédicat path → bool (attendu exact OU sous-chaîne), comme first_relevant_rank."""
    exact = set(entry.get("expected_paths") or [])
    fragments = list(entry.get("expected_path_contains") or [])

    def matches(path: str) -> bool:
        return path in exact or any(frag in path for frag in fragments)

    return matches


def _rank_of_expected(hits: list[dict[str, Any]], entry: dict[str, Any]) -> int | None:
    """Rang du doc attendu dans une liste par canal (None = absent)."""
    matches = _expected_matcher(entry)
    for h in hits:
        if matches(h.get("path", "")):
            return h.get("rank")
    return None


# Verdicts déterministes + hypothèses PROPOSÉES (jamais appliquées — SR1.3).
_VERDICTS: dict[str, tuple[str, list[str]]] = {
    "absent_both": (
        "absent des deux canaux — le doc n'est remonté ni sémantiquement ni littéralement",
        [
            "vérifier que le document est bien indexé (index_status)",
            "revoir la stratégie de chunking (granularité, régions)",
            "activer/renforcer le contexte à l'embedding (F6) pour ce type de doc",
        ],
    ),
    "vector_only": (
        "présent au canal VECTORIEL uniquement — le canal lexical ne le trouve pas",
        [
            "la requête ne partage pas les tokens littéraux du doc (reformulation lexicale)",
            "monter le curseur de pondération vectorielle",
        ],
    ),
    "lexical_only": (
        "présent au canal LEXICAL uniquement — l'embedding ne le rapproche pas",
        [
            "écart sémantique : modèle d'embedding ou contexte F6 insuffisant",
            "monter le curseur de pondération lexicale",
        ],
    ),
    "drowned_fusion": (
        "présent dans LES DEUX canaux mais noyé à la fusion (hors top_k fusionné)",
        [
            "d'autres documents dominent la fusion : ajuster les curseurs de pondération",
            "augmenter top_k ou baisser rrf_k",
        ],
    ),
    "vector_low_rank": (
        "présent au canal vectoriel mais à un rang trop bas (baseline vectoriel-seul)",
        [
            "rang au-delà du top_k : améliorer l'embedding ou le contexte F6",
            "augmenter top_k pour confirmer la présence",
        ],
    ),
}


def classify_failure(entry: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Classe un échec à partir des canaux (D8) — analyse structurelle, sans LLM.

    Détermine le rang du doc attendu dans chaque canal et en déduit un verdict :
    absent des deux, présent dans un seul canal, ou noyé à la fusion. En baseline
    vectoriel-seul (canal lexical vide) le verdict se limite au canal unique.
    """
    channels = payload.get("channels") or {}
    vector_rank = _rank_of_expected(channels.get("vector") or [], entry)
    lexical_rank = _rank_of_expected(channels.get("lexical") or [], entry)
    has_lexical = bool(channels.get("lexical"))

    if vector_rank is None and lexical_rank is None:
        verdict = "absent_both"
    elif vector_rank is not None and lexical_rank is not None:
        verdict = "drowned_fusion"
    elif vector_rank is not None:
        verdict = "vector_only" if has_lexical else "vector_low_rank"
    else:
        verdict = "lexical_only"

    label, hypotheses = _VERDICTS[verdict]
    return {
        "verdict": verdict,
        "label": label,
        "vector_rank": vector_rank,
        "lexical_rank": lexical_rank,
        "hypotheses": hypotheses,
    }


def render_diagnosis(
    failures: list[tuple[dict[str, Any], dict[str, Any]]], *, workspace: str, top_k: int
) -> str:
    """Dossier de diagnostic par échec (SR1.3) — analyse structurelle par canal
    (D8) + hypothèses PROPOSÉES, plus les listes brutes pour l'agent diagnosticien."""
    lines = [
        "# Dossier de diagnostic des échecs",
        "",
        f"- Workspace : `{workspace}` — top_k={top_k}",
        f"- {len(failures)} échec(s) — un bloc par question, à donner tel quel",
        "  à l'agent diagnosticien (prompts v1, bloc Recherche).",
    ]
    for entry, payload in failures:
        expected = entry.get("expected_paths") or entry.get("expected_path_contains")
        diag = classify_failure(entry, payload)
        ranks = f"vectoriel={diag['vector_rank']} lexical={diag['lexical_rank']}"
        lines += [
            "",
            f"## {entry['query']}",
            "",
            f"- famille : {entry.get('family', 'sans-famille')} — attendu : {expected}",
            f"- **verdict** : {diag['label']} (rangs : {ranks})",
            "- hypothèses proposées (non appliquées) :",
            *[f"  - {h}" for h in diag["hypotheses"]],
            "- fusion (top hits) :",
        ]
        for h in payload.get("results", []):
            lines.append(f"  - {h['path']}#{h['chunk_index']} score={h['score']:.3f}")
        channels = payload.get("channels") or {}
        for name in ("vector", "lexical"):
            lines.append(f"- canal {name} :")
            hits = channels.get(name) or []
            if not hits:
                lines.append("  - (vide)")
            for h in hits[:10]:
                lines.append(f"  - rang {h['rank']} : {h['path']}#{h['chunk_index']}")
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
    parser.add_argument(
        "--config-note",
        help="configuration testée, reprise dans le rapport "
        "(moteur, curseurs, contexte F6 actif ou non)",
    )
    parser.add_argument(
        "--diagnose",
        help="chemin du dossier de diagnostic : re-joue chaque échec de la "
        "dernière passe avec debug=true et dumpe fusion + canaux (SR1.3)",
    )
    args = parser.parse_args()
    if not args.api_key:
        sys.exit("clé API requise : --api-key ou env RAG_BENCH_API_KEY")

    golden = load_golden(args.golden)
    print(
        f"Jeu : {golden.version or 'non versionné'} — {len(golden.queries)} question(s) "
        f"— {args.passes} passe(s), top_k={args.top_k}"
    )

    all_ranks: list[list[int | None]] = []
    with httpx.Client() as client:
        for i in range(args.passes):
            ranks = run_pass(
                client,
                base_url=args.base_url,
                workspace=args.workspace,
                api_key=args.api_key,
                golden=golden.queries,
                top_k=args.top_k,
            )
            all_ranks.append(ranks)
            pass_metrics = metrics(ranks)
            summary = "  ".join(f"{k}={v:.3f}" for k, v in pass_metrics.items())
            print(f"  passe {i + 1}: {summary}")

    report = render_report(
        golden,
        all_ranks,
        workspace=args.workspace,
        top_k=args.top_k,
        config_note=args.config_note,
    )
    print("\n" + report)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"Rapport écrit : {args.report}")

    if args.diagnose:
        failed = [golden.queries[i] for i, r in enumerate(all_ranks[-1]) if r is None]
        with httpx.Client() as client:
            failures = [
                (
                    entry,
                    search_debug(
                        client,
                        args.base_url,
                        args.workspace,
                        args.api_key,
                        entry["query"],
                        args.top_k,
                    ),
                )
                for entry in failed
            ]
        diagnosis = render_diagnosis(failures, workspace=args.workspace, top_k=args.top_k)
        with open(args.diagnose, "w", encoding="utf-8") as fh:
            fh.write(diagnosis)
        print(f"Diagnostic écrit : {args.diagnose} ({len(failures)} échec(s))")


if __name__ == "__main__":
    main()
