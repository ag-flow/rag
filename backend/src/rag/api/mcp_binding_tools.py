from __future__ import annotations

from contextvars import ContextVar
from typing import Any

import structlog

from rag.api.mcp_library_support import (
    EXPECTED_ERRORS,
    dump,
    explain,
    parse_uuid,
    write_refusal,
)
from rag.schemas.chunking_strategies import RoutesUpdate, StrategyPromptsUpdate
from rag.services import chunking_strategies as strategies_svc

log = structlog.get_logger(__name__)


def register_binding_tools(mcp: Any, ws_ctx: ContextVar[Any]) -> None:
    """Outils MCP de composition d'une stratégie : routes de régions + prompts."""

    @mcp.tool()
    async def set_chunking_strategy_routes(strategy_id: str, routes: list[dict[str, Any]]) -> str:
        """Remplace le jeu COMPLET de routes de régions d'une de tes stratégies.

        Prérequis : la stratégie a un parser_slug (passe régions active) et
        t'appartient. can_write requis. Résolution à l'indexation : route exacte
        (type, qualifier) > wildcard (type, '*') > inline (algo parent).

        routes : liste d'objets —
        - region_type (obligatoire) : 'prose' | 'code_fence' | 'table' |
          'frontmatter' | 'html_block' (taxonomie fermée).
        - qualifier (défaut '*') : sous-type ouvert — ex. 'mermaid' ou 'python'
          pour un code_fence ; '*' = toutes les régions du type.
        - target_strategy_id (défaut null) : UUID d'une stratégie visible (système
          ou tienne) qui traite la région ; null = traitement inline.
        - atomic (défaut false) : la région n'est jamais découpée (un seul chunk).
        - overflow_policy (défaut 'keep_whole') : si une région atomique dépasse la
          limite de tokens —
          - 'keep_whole'     : erreur à l'indexation si trop gros (garantie forte) ;
          - 'split_fallback' : renonce à l'atomicité et découpe quand même ;
          - 'parent_only'    : jamais embeddée, mais restituée au LLM dans la
            section parente au moment de la recherche.
        Deux routes ne peuvent pas partager le même couple (type, qualifier).

        Effet de bord : REMPLACE toutes les routes existantes (liste vide = tout
        retirer). Sortie : JSON des routes en base après écriture.
        """
        ctx = ws_ctx.get()
        refusal = write_refusal(ctx)
        if refusal:
            return refusal
        try:
            sid = parse_uuid(strategy_id)
            spec = RoutesUpdate(routes=routes)
            async with ctx.config_pool.acquire() as conn:
                out = await strategies_svc.set_region_routes(
                    conn, owner_id=ctx.owner_id, strategy_id=sid, routes=spec.routes
                )
        except EXPECTED_ERRORS as exc:
            return explain(exc)
        return dump(out)

    @mcp.tool()
    async def set_chunking_strategy_prompts(strategy_id: str, prompts: list[dict[str, Any]]) -> str:
        """Remplace le jeu de prompts de contexte liés à une de tes stratégies.

        Seuls les templates en timing embedding_inline (modes chunk ou region)
        sont liables — un template en mode document est refusé : crée-le en mode
        chunk ou région. Un target region:* exige un parser_slug sur la stratégie.
        can_write requis.

        AVERTISSEMENT : embedding_inline modifie le texte embeddé donc les
        VECTEURS — une réindexation est nécessaire pour prendre effet sur les
        documents existants. Un binding n'est jamais actif par défaut ailleurs :
        c'est `enabled` ici qui contrôle l'activation.

        prompts : liste d'objets —
        - template_id (obligatoire) : UUID d'un template visible (voir
          list_prompt_templates).
        - order_index (défaut 1, ≥1) : ordre d'application des prompts.
        - enabled (défaut true) : binding actif ou suspendu.
        Un même template ne peut pas être lié deux fois.

        Effet de bord : REMPLACE tous les bindings existants (liste vide = tout
        délier). Sortie : JSON des bindings en base après écriture.
        """
        ctx = ws_ctx.get()
        refusal = write_refusal(ctx)
        if refusal:
            return refusal
        try:
            sid = parse_uuid(strategy_id)
            spec = StrategyPromptsUpdate(prompts=prompts)
            async with ctx.config_pool.acquire() as conn:
                out = await strategies_svc.set_strategy_prompts(
                    conn, owner_id=ctx.owner_id, strategy_id=sid, prompts=spec.prompts
                )
        except EXPECTED_ERRORS as exc:
            return explain(exc)
        return dump(out)
