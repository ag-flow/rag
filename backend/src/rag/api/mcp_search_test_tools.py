from __future__ import annotations

from contextvars import ContextVar
from typing import Any

import structlog

from rag.api.mcp_library_support import dump, parse_uuid
from rag.services import search_test as svc

log = structlog.get_logger(__name__)

_WRITE_REFUSAL = (
    "Écriture refusée : alimenter le banc de test exige une clé de niveau "
    "'read_write' ou 'admin' sur ce workspace."
)


def register_search_test_tools(mcp: Any, ws_ctx: ContextVar[Any]) -> None:
    """Banc de test de recherche (feature 1a9b8b67) : les agents poussent les
    questions avec leur réponse attendue en parcourant docflow ;
    `run_search_test_campaign` lance la campagne (aussi possible depuis
    l'IHM) ; `get_search_test_report` expose les résultats détaillés — attendu
    ET retourné — pour l'analyse (diagnostic, comparaison avant/après)."""

    def _write_refusal(ctx: Any) -> str | None:
        return None if ctx.scope in ("read_write", "admin") else _WRITE_REFUSAL

    async def _ws_id(ctx: Any, workspace: str) -> Any:
        from rag.api.mcp_standard import _resolve_ws

        return (await _resolve_ws(ctx, workspace)).workspace_id

    @mcp.tool()
    async def push_test_question(
        workspace: str,
        question: str,
        expected_path_contains: str,
        family: str = "libre",
    ) -> str:
        """Pousse (upsert) une question de test avec sa réponse attendue.

        Le banc mesure la qualité de recherche par PROVENANCE : la question est
        posée au moteur et on vérifie que le document attendu ressort dans le
        top-10 — verdict arithmétique, sans jugement LLM.

        - workspace : slug du workspace (voir list_workspaces)
        - question  : question en français naturel d'utilisateur réel
        - expected_path_contains : fragment du path du document attendu dans
          l'index (ex. l'UUID docflow du document source — visible dans les
          paths poussés)
        - family    : litterale (terme exact de la page — teste le lexical) |
          paraphrasee (sans le vocabulaire clé — teste le vectoriel) |
          indirecte (besoin utilisateur dont la page est la réponse) | libre

        Upsert par (workspace, question). Requiert une clé 'read_write' ou
        'admin'. La campagne se lance via run_search_test_campaign ou depuis
        l'IHM (onglet Banc de test).
        """
        ctx = ws_ctx.get()
        refusal = _write_refusal(ctx)
        if refusal:
            return refusal
        ws_id = await _ws_id(ctx, workspace)
        try:
            row = await svc.upsert_question(
                ctx.config_pool,
                workspace_id=ws_id,
                question=question,
                expected_path_contains=expected_path_contains,
                family=family,
            )
        except ValueError as exc:
            return f"Question refusée : {exc}"
        log.info("mcp.search_test.pushed", workspace=workspace, family=family)
        return dump(row)

    @mcp.tool()
    async def list_test_questions(workspace: str) -> str:
        """Liste les questions du banc de test d'un workspace (id, question,
        fragment attendu, famille, activée). Lecture seule, toute clé valide."""
        ctx = ws_ctx.get()
        ws_id = await _ws_id(ctx, workspace)
        return dump(await svc.list_questions(ctx.config_pool, workspace_id=ws_id))

    @mcp.tool()
    async def delete_test_question(workspace: str, question_id: str) -> str:
        """Supprime une question du banc (id retourné par list_test_questions).
        Requiert une clé 'read_write' ou 'admin'."""
        ctx = ws_ctx.get()
        refusal = _write_refusal(ctx)
        if refusal:
            return refusal
        ws_id = await _ws_id(ctx, workspace)
        ok = await svc.delete_question(
            ctx.config_pool, workspace_id=ws_id, question_id=parse_uuid(question_id)
        )
        return dump({"deleted": ok})

    @mcp.tool()
    async def run_search_test_campaign(workspace: str) -> str:
        """Lance une campagne du banc de test et retourne son résumé.

        Chaque question ACTIVÉE est posée à la recherche du produit (config
        hybride du workspace respectée, top-10) ; le run est historisé avec,
        pour chaque question, le rang du document attendu ET le top-10
        retourné (path, score, extrait) — consultable ensuite via
        get_search_test_report ou l'IHM (onglet Banc de test).

        Sortie : {id (run_id), started_at, config, metrics (recall@1/5/10,
        mrr — globaux et par famille), questions_total, questions_failed}.
        L'historique des runs est conservé 72 h puis purgé automatiquement —
        exploiter un rapport sans tarder. Requiert une clé 'read_write' ou
        'admin'. Attention : la campagne
        consomme des appels d'embedding (une recherche par question).
        """
        from rag.api.mcp_standard import _resolve_ws
        from rag.api.playground import make_harpo_resolver_from
        from rag.api.search_test_campaign import launch_campaign

        ctx = ws_ctx.get()
        refusal = _write_refusal(ctx)
        if refusal:
            return refusal.replace("alimenter le banc de test", "lancer une campagne")
        ws = await _resolve_ws(ctx, workspace)
        try:
            run = await launch_campaign(
                config_pool=ctx.config_pool,
                pool_registry=ctx.pool_registry,
                resolve_harpo=make_harpo_resolver_from(
                    config_pool=ctx.config_pool,
                    vault_svc=ctx.vaults_service,
                    client_provider=ctx.client_provider,
                ),
                workspace_id=ws.workspace_id,
                workspace_name=ws.workspace_name,
            )
        except ValueError as exc:
            return f"Campagne refusée : {exc}"
        summary = {k: v for k, v in run.items() if k != "results"}
        return dump(summary)

    @mcp.tool()
    async def get_search_test_report(workspace: str, run_id: str = "") -> str:
        """Résultats détaillés du banc de test : dernier run (défaut) ou run
        précis — la matière d'analyse d'un agent diagnosticien.

        Sortie : {id, started_at, config (hybride, moteur, pondérations,
        top_k), metrics (recall@1/5/10, mrr — globaux et par famille),
        questions_total, questions_failed, results: [{question, family,
        expected_path_contains (CE QUI ÉTAIT ATTENDU : fragment du path du
        document), rank (rang où il est ressorti — null = absent du top-k),
        error (échec d'appel de la recherche, sinon null),
        returned: [{rank, path, score, snippet, matched}] (CE QUI EST REVENU,
        ordonné)}]}. Comparer expected_path_contains aux returned[].path d'un
        échec montre quels documents ont pris la place et avec quels scores.
        Historique conservé 72 h puis purgé. Lecture seule, toute clé valide.
        """
        ctx = ws_ctx.get()
        ws_id = await _ws_id(ctx, workspace)
        if run_id:
            run = await svc.get_run(ctx.config_pool, workspace_id=ws_id, run_id=parse_uuid(run_id))
        else:
            runs = await svc.list_runs(ctx.config_pool, workspace_id=ws_id, limit=1)
            run = (
                await svc.get_run(ctx.config_pool, workspace_id=ws_id, run_id=runs[0]["id"])
                if runs
                else None
            )
        if run is None:
            return (
                "Aucun run pour ce workspace — lance une campagne via "
                "run_search_test_campaign ou depuis l'IHM (onglet Banc de test)."
            )
        return dump(run)
