from __future__ import annotations

from contextvars import ContextVar
from typing import Any

import structlog

from rag.api.mcp_binding_tools import register_binding_tools
from rag.api.mcp_library_support import (
    EXPECTED_ERRORS,
    dump,
    explain,
    parse_uuid,
    write_refusal,
)
from rag.api.mcp_prompt_tools import register_prompt_tools
from rag.schemas.chunking_strategies import StrategyCreate, StrategyPatch
from rag.services import chunking_strategies as strategies_svc

log = structlog.get_logger(__name__)


def register_library_tools(mcp: Any, ws_ctx: ContextVar[Any]) -> None:
    """Enregistre les outils MCP de gestion de la bibliothèque utilisateur.

    Stratégies de chunking (CRUD + duplicate + routes + bindings de prompts)
    puis templates de prompts (via register_prompt_tools). Le contexte requête
    (owner_id, scope, config_pool) vient du ContextVar posé par le
    dispatcher — mêmes gardes métier que l'IHM (services owner-scoped).
    """

    @mcp.tool()
    async def list_chunking_strategies() -> str:
        """Liste la bibliothèque de stratégies de chunking et les parsers de régions.

        La bibliothèque contient les stratégies système (partagées, lecture seule)
        et les tiennes. Une stratégie = un algo de découpe + des paramètres + un
        éventuel parser de régions pour le routage intra-document.

        Workflow recommandé pour composer une stratégie de bout en bout :
        1. list_chunking_strategies() — repérer l'existant et les parsers disponibles.
        2. create_chunking_strategy(...) ou duplicate_chunking_strategy(...) depuis
           une stratégie système proche du besoin.
        3. set_chunking_strategy_routes(...) — router les régions (exige parser_slug).
        4. list_prompt_templates() puis set_chunking_strategy_prompts(...) — lier des
           prompts de contexte à l'embedding (modes chunk/region).

        Sortie : JSON {"parsers": [{slug, label}], "strategies": [...]} — chaque
        stratégie : id, label, slug, algo, params, parser_slug, is_system,
        compteurs d'usage (used_by_routes/triggers/workspaces), dates.
        Lecture seule.
        """
        ctx = ws_ctx.get()
        async with ctx.config_pool.acquire() as conn:
            parsers = await strategies_svc.list_parsers(conn)
            strategies = await strategies_svc.list_strategies(conn, owner_id=ctx.owner_id)
        return dump({"parsers": parsers, "strategies": strategies})

    @mcp.tool()
    async def get_chunking_strategy(strategy_id: str) -> str:
        """Détail complet d'une stratégie : paramètres, routes de régions, prompts liés.

        Paramètres :
        - strategy_id : UUID de la stratégie (obtenu via list_chunking_strategies).

        Sortie : JSON de la stratégie avec `routes` (routage des régions) et
        `prompts` (templates liés à l'embedding, avec order_index et enabled).
        Lecture seule. Message d'erreur si l'id est inconnu ou invisible.
        """
        ctx = ws_ctx.get()
        try:
            sid = parse_uuid(strategy_id)
            async with ctx.config_pool.acquire() as conn:
                out = await strategies_svc.get_strategy(
                    conn, owner_id=ctx.owner_id, strategy_id=sid
                )
        except EXPECTED_ERRORS as exc:
            return explain(exc)
        return dump(out)

    @mcp.tool()
    async def create_chunking_strategy(
        label: str,
        algo: str,
        parser_slug: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        """Crée une stratégie de chunking dans ta bibliothèque (grant niveau admin requis).

        Le slug est dérivé du label côté serveur (jamais saisi) ; l'algo est figé
        après création — seuls label, params et parser restent modifiables.

        Algos disponibles :
        - prose : découpe hiérarchique small-to-big — le document est scindé par ses
          titres en sections parentes, puis en chunks enfants bornés en tokens ; le
          fil de titres (breadcrumb) est injecté dans le texte embeddé. À la requête
          le chunk matche, la section parente est restituée au LLM. Idéal :
          documentation, wikis, README. Conseil : cible 384 tokens, titres H1-H2 ;
          ajouter un parser de régions pour router fences et tableaux.
        - markdown : alias de prose (même moteur) — nomme clairement les stratégies
          dédiées aux corpus Markdown. Les fences ``` ne sont jamais coupées.
        - table : groupes de lignes avec l'en-tête répété sur chaque chunk (chaque
          morceau reste interprétable seul). Idéal : CSV/TSV, tableaux de référence.
          Conseil : ajuster max_rows_per_chunk (défaut 50).
        - code : symboles tree-sitter (fonctions, classes, méthodes) avec breadcrumb
          de portée (module > classe > méthode) ; repli gracieux en prose si le
          langage n'est pas supporté. Conseil : overlap 0, floor 128 tokens.
        - data : clés de premier niveau (JSON/YAML/TOML via tree-sitter) — un chunk
          = une entrée cohérente, jamais un objet coupé en deux. Conseil : overlap 0.

        params (dict, toutes clés optionnelles ; clé inconnue pour l'algo → rejet) :
        - child_target_tokens (int, défaut 384) : taille cible d'un chunk embeddé ;
          plus grand = plus de contexte mais recherche moins précise. Toujours
          plafonné par la limite du modèle d'embedding (marge de sécurité 20 %).
        - floor_tokens (int, défaut 64 ; 128 conseillé pour code) : taille minimale —
          les fragments plus petits sont fusionnés avec leurs voisins (pas de
          chunk-miette sans valeur sémantique).
        - overlap_tokens (int, défaut 64 ; 0 conseillé pour code et data) :
          chevauchement entre chunks consécutifs pour ne jamais couper une idée à
          la frontière ; inutile quand les frontières sont naturelles.
        - breadcrumb_depth (int, défaut -1 = chemin complet, recommandé) :
          profondeur du fil de titres injecté en tête du texte embeddé
          (ex. « Guide > Install ») — améliore nettement le retrieval.
        - heading_levels (liste d'entiers, défaut [1, 2] ; prose/markdown
          uniquement) : niveaux de titres Markdown ouvrant une section parente
          ([1, 2] = H1 et H2 ; ajouter 3 affine les gros documents).
        - max_rows_per_chunk (int, défaut 50 ; table uniquement) : lignes de données
          max par chunk, en-tête répété — à baisser pour des lignes larges.
        - clean_content, strip_separators, strip_boilerplate, strip_html (bool,
          défaut false) : options de nettoyage indépendantes du texte avant découpe.

        Clés autorisées par algo — prose/markdown : child_target_tokens,
        floor_tokens, overlap_tokens, breadcrumb_depth, heading_levels + nettoyage ;
        code/data : idem sans heading_levels ; table : child_target_tokens,
        max_rows_per_chunk + nettoyage.

        parser_slug : active la passe régions (routage intra-document via
        set_chunking_strategy_routes) — prose/markdown uniquement. Parsers
        disponibles dans la sortie de list_chunking_strategies() (ex. 'markdown').

        Sortie : JSON de la stratégie créée. Erreurs en message clair (slug déjà
        utilisé, algo/param/parser invalide) — jamais d'exception.
        """
        ctx = ws_ctx.get()
        refusal = write_refusal(ctx)
        if refusal:
            return refusal
        try:
            req = StrategyCreate(
                label=label, algo=algo, params=params or {}, parser_slug=parser_slug
            )
            async with ctx.config_pool.acquire() as conn:
                out = await strategies_svc.create_strategy(conn, owner_id=ctx.owner_id, req=req)
        except EXPECTED_ERRORS as exc:
            return explain(exc)
        log.info("mcp_library.strategy_created", strategy_id=str(out.id))
        return dump(out)

    @mcp.tool()
    async def update_chunking_strategy(
        strategy_id: str,
        label: str | None = None,
        params: dict[str, Any] | None = None,
        parser_slug: str | None = None,
        remove_parser: bool = False,
    ) -> str:
        """Modifie une de TES stratégies (niveau admin requis) — les système sont immuables.

        Seuls les champs fournis changent ; l'algo est figé après création.
        - label : renommer — le slug est re-dérivé côté serveur.
        - params : REMPLACE le dict complet de paramètres (pas de fusion) — repars
          du détail via get_chunking_strategy. Mêmes clés que create_chunking_strategy.
        - parser_slug : pose ou change le parser de régions (prose/markdown).
        - remove_parser=true : retire la passe régions (parser_slug remis à null).

        Attention : si la stratégie est utilisée (routes, triggers, workspaces),
        la modification change immédiatement le comportement d'indexation partagé.
        Sortie : JSON de la stratégie à jour, ou message d'erreur explicite.
        """
        ctx = ws_ctx.get()
        refusal = write_refusal(ctx)
        if refusal:
            return refusal
        try:
            fields: dict[str, Any] = {}
            if label is not None:
                fields["label"] = label
            if params is not None:
                fields["params"] = params
            if remove_parser:
                fields["parser_slug"] = None
            elif parser_slug is not None:
                fields["parser_slug"] = parser_slug
            sid = parse_uuid(strategy_id)
            async with ctx.config_pool.acquire() as conn:
                out = await strategies_svc.patch_strategy(
                    conn, owner_id=ctx.owner_id, strategy_id=sid, req=StrategyPatch(**fields)
                )
        except EXPECTED_ERRORS as exc:
            return explain(exc)
        return dump(out)

    @mcp.tool()
    async def delete_chunking_strategy(strategy_id: str) -> str:
        """Supprime une de TES stratégies (niveau admin requis).

        Refusé avec un message détaillé si la stratégie est référencée : cible de
        routes d'autres stratégies, triggers d'extension ou stratégie par défaut
        de workspaces — détache ces références d'abord. Les stratégies système
        ne sont jamais supprimables.
        """
        ctx = ws_ctx.get()
        refusal = write_refusal(ctx)
        if refusal:
            return refusal
        try:
            sid = parse_uuid(strategy_id)
            async with ctx.config_pool.acquire() as conn:
                await strategies_svc.delete_strategy(conn, owner_id=ctx.owner_id, strategy_id=sid)
        except EXPECTED_ERRORS as exc:
            return explain(exc)
        return f"Stratégie {strategy_id} supprimée."

    @mcp.tool()
    async def duplicate_chunking_strategy(strategy_id: str, label: str) -> str:
        """Copie une stratégie visible (système ou tienne) dans ta bibliothèque.

        C'est LA voie pour personnaliser une stratégie système (immuable) : la
        copie t'appartient et reprend params, routes de régions et bindings de
        prompts. niveau admin requis.

        Paramètres :
        - strategy_id : UUID de la stratégie source.
        - label : label de la copie (le slug en est dérivé — doit rester unique).

        Sortie : JSON de la nouvelle stratégie (routes et prompts inclus).
        """
        ctx = ws_ctx.get()
        refusal = write_refusal(ctx)
        if refusal:
            return refusal
        try:
            sid = parse_uuid(strategy_id)
            async with ctx.config_pool.acquire() as conn:
                out = await strategies_svc.duplicate_strategy(
                    conn, owner_id=ctx.owner_id, source_id=sid, label=label
                )
        except EXPECTED_ERRORS as exc:
            return explain(exc)
        return dump(out)

    register_binding_tools(mcp, ws_ctx)
    register_prompt_tools(mcp, ws_ctx)
