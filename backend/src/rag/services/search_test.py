"""Banc de test de recherche intégré — feature docflow 1a9b8b67.

Les questions (avec le fragment de path attendu — l'UUID docflow du doc
source) sont poussées par les agents via MCP, la campagne se lance depuis
l'IHM, les runs sont persistés (migration 092). Verdict purement arithmétique
par provenance (D9) : rang du doc attendu, recall@k et MRR, globaux et par
famille — logique portée de scripts/retrieval_bench.py.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import asyncpg
import structlog

log = structlog.get_logger(__name__)

RECALL_KS = (1, 5, 10)
FAMILIES = ("litterale", "paraphrasee", "indirecte", "libre")

# Rétention de l'historique des campagnes (décision architecte 2026-07-28) :
# les runs sont une matière de diagnostic, purgés automatiquement après 72 h
# (le DELETE cascade sur search_test_run_results). Les QUESTIONS, elles, sont
# permanentes.
RUNS_RETENTION_HOURS = 72

# Le run appelle la recherche du produit : question → hits ordonnés
# [{path, score, chunk_index, snippet}] — le détail retourné est persisté
# avec chaque résultat pour l'analyse (migration 093).
SearchFn = Callable[[str], Awaitable[list[dict[str, Any]]]]


def first_relevant_rank(paths: list[str], fragment: str) -> int | None:
    """Rang (1-indexé) du premier résultat dont le path contient le fragment."""
    for rank, path in enumerate(paths, start=1):
        if fragment in path:
            return rank
    return None


def aggregate_metrics(entries: list[tuple[str, int | None]]) -> dict[str, Any]:
    """recall@k + MRR, globaux et par famille — verdict arithmétique (D9)."""

    def _metrics(ranks: list[int | None]) -> dict[str, float]:
        n = len(ranks) or 1
        out = {
            f"recall@{k}": round(sum(1 for r in ranks if r is not None and r <= k) / n, 4)
            for k in RECALL_KS
        }
        out["mrr"] = round(sum(1.0 / r for r in ranks if r is not None) / n, 4)
        return out

    result: dict[str, Any] = _metrics([r for _, r in entries])
    families: dict[str, Any] = {}
    for family in sorted({f for f, _ in entries}):
        families[family] = _metrics([r for f, r in entries if f == family])
    result["families"] = families
    return result


# --- CRUD questions -------------------------------------------------------


async def upsert_question(
    pool: asyncpg.Pool,
    *,
    workspace_id: UUID,
    question: str,
    expected_path_contains: str,
    family: str = "libre",
) -> dict[str, Any]:
    if family not in FAMILIES:
        raise ValueError(f"famille invalide : {family!r} (attendu : {', '.join(FAMILIES)})")
    row = await pool.fetchrow(
        """
        INSERT INTO search_test_questions
            (workspace_id, question, expected_path_contains, family)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (workspace_id, question) DO UPDATE
        SET expected_path_contains = EXCLUDED.expected_path_contains,
            family = EXCLUDED.family
        RETURNING id, question, expected_path_contains, family, enabled, created_at
        """,
        workspace_id,
        question.strip(),
        expected_path_contains.strip(),
        family,
    )
    return dict(row)


async def list_questions(pool: asyncpg.Pool, *, workspace_id: UUID) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        "SELECT id, question, expected_path_contains, family, enabled, created_at "
        "FROM search_test_questions WHERE workspace_id = $1 ORDER BY created_at",
        workspace_id,
    )
    return [dict(r) for r in rows]


async def set_question_enabled(
    pool: asyncpg.Pool, *, workspace_id: UUID, question_id: UUID, enabled: bool
) -> bool:
    status = await pool.execute(
        "UPDATE search_test_questions SET enabled = $3 WHERE workspace_id = $1 AND id = $2",
        workspace_id,
        question_id,
        enabled,
    )
    return status != "UPDATE 0"


async def delete_question(pool: asyncpg.Pool, *, workspace_id: UUID, question_id: UUID) -> bool:
    status = await pool.execute(
        "DELETE FROM search_test_questions WHERE workspace_id = $1 AND id = $2",
        workspace_id,
        question_id,
    )
    return status != "DELETE 0"


# --- Campagne -------------------------------------------------------------


async def run_campaign(
    pool: asyncpg.Pool,
    *,
    workspace_id: UUID,
    search_fn: SearchFn,
    config: dict[str, Any],
    top_k: int = 10,
) -> dict[str, Any]:
    """Exécute la campagne sur les questions ACTIVÉES et persiste le run.

    `search_fn(question)` = la recherche du produit (config hybride du
    workspace respectée), retourne les hits ordonnés [{path, score,
    chunk_index, snippet}] — persistés avec chaque résultat (attendu vs
    retourné, migration 093). Une question en échec d'appel N'interrompt pas
    la campagne : rang absent + erreur historisée.
    """
    questions = [q for q in await list_questions(pool, workspace_id=workspace_id) if q["enabled"]]
    if not questions:
        raise ValueError("aucune question activée pour ce workspace")

    entries: list[tuple[str, int | None]] = []
    results: list[dict[str, Any]] = []
    for q in questions:
        error: str | None = None
        try:
            hits = await search_fn(q["question"])
        except Exception as exc:
            log.warning("search_test.question_failed", question=q["question"], error=str(exc))
            hits, error = [], str(exc)
        hits = hits[:top_k]
        fragment = q["expected_path_contains"]
        rank = first_relevant_rank([h["path"] for h in hits], fragment)
        entries.append((q["family"], rank))
        results.append(
            {
                "question": q["question"],
                "family": q["family"],
                "expected_path_contains": fragment,
                "rank": rank,
                "error": error,
                # Ce qui est REVENU, ordonné — matière première de l'analyse.
                "returned": [
                    {**h, "rank": i + 1, "matched": fragment in h["path"]}
                    for i, h in enumerate(hits)
                ],
            }
        )

    metrics = aggregate_metrics(entries)
    failed = sum(1 for _, r in entries if r is None)
    async with pool.acquire() as conn, conn.transaction():
        run = await conn.fetchrow(
            """
            INSERT INTO search_test_runs
                (workspace_id, config, metrics, questions_total, questions_failed)
            VALUES ($1, $2::jsonb, $3::jsonb, $4, $5)
            RETURNING id, started_at
            """,
            workspace_id,
            json.dumps({**config, "top_k": top_k}),
            json.dumps(metrics),
            len(questions),
            failed,
        )
        for r in results:
            await conn.execute(
                "INSERT INTO search_test_run_results "
                "(run_id, question, family, expected_path_contains, rank, returned, error) "
                "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)",
                run["id"],
                r["question"],
                r["family"],
                r["expected_path_contains"],
                r["rank"],
                json.dumps(r["returned"]),
                r["error"],
            )
    log.info(
        "search_test.run_done",
        workspace_id=str(workspace_id),
        run_id=str(run["id"]),
        total=len(questions),
        failed=failed,
    )
    return {
        "id": run["id"],
        "started_at": run["started_at"],
        "config": {**config, "top_k": top_k},
        "metrics": metrics,
        "questions_total": len(questions),
        "questions_failed": failed,
        "results": results,
    }


async def list_runs(
    pool: asyncpg.Pool, *, workspace_id: UUID, limit: int = 20
) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        "SELECT id, started_at, config, metrics, questions_total, questions_failed "
        "FROM search_test_runs WHERE workspace_id = $1 ORDER BY started_at DESC LIMIT $2",
        workspace_id,
        limit,
    )
    return [_run_to_dict(r) for r in rows]


async def get_run(pool: asyncpg.Pool, *, workspace_id: UUID, run_id: UUID) -> dict[str, Any] | None:
    row = await pool.fetchrow(
        "SELECT id, started_at, config, metrics, questions_total, questions_failed "
        "FROM search_test_runs WHERE workspace_id = $1 AND id = $2",
        workspace_id,
        run_id,
    )
    if row is None:
        return None
    run = _run_to_dict(row)
    results = await pool.fetch(
        "SELECT question, family, expected_path_contains, rank, returned, error "
        "FROM search_test_run_results WHERE run_id = $1 ORDER BY family, question",
        run_id,
    )

    def _parse_returned(value: Any) -> Any:
        return json.loads(value) if isinstance(value, str) else value

    run["results"] = [{**dict(r), "returned": _parse_returned(r["returned"])} for r in results]
    return run


async def purge_old_runs(pool: asyncpg.Pool) -> int:
    """Purge les runs plus vieux que RUNS_RETENTION_HOURS (entretien worker).

    Retourne le nombre de runs supprimés (les résultats suivent par cascade).
    """
    status = await pool.execute(
        "DELETE FROM search_test_runs WHERE started_at < now() - make_interval(hours => $1)",
        RUNS_RETENTION_HOURS,
    )
    count = int(status.split()[-1])
    if count:
        log.info("search_test.runs_purged", count=count, retention_hours=RUNS_RETENTION_HOURS)
    return count


def _run_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    out = dict(row)
    for key in ("config", "metrics"):
        if isinstance(out[key], str):
            out[key] = json.loads(out[key])
    return out
