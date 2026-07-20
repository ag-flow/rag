from __future__ import annotations

from contextvars import ContextVar
from typing import Any

import structlog

from rag.api.mcp_library_support import EXPECTED_ERRORS, dump, explain, write_refusal
from rag.schemas.enrichments import PromptTemplateCreate, PromptTemplatePatch
from rag.services import prompt_templates as templates_svc

log = structlog.get_logger(__name__)

_REGION_TYPES_HELP = "'prose' | 'code_fence' | 'table' | 'frontmatter' | 'html_block'"


def _derive_axes(
    mode: str, region_type: str | None, region_qualifier: str | None
) -> tuple[str, str]:
    """Dérive (target, timing) du mode — mêmes règles que l'IHM (buildAxes)."""
    if mode == "document":
        return "document", "post_index_metadata"
    if mode == "chunk":
        return "chunk", "embedding_inline"
    if mode == "region":
        if not region_type:
            raise ValueError(f"mode 'region' : region_type est obligatoire ({_REGION_TYPES_HELP})")
        qualifier = (region_qualifier or "").strip()
        target = f"region:{region_type}:{qualifier}" if qualifier else f"region:{region_type}"
        return target, "embedding_inline"
    raise ValueError(f"mode inconnu : {mode!r} — attendu 'document', 'chunk' ou 'region'")


def register_prompt_tools(mcp: Any, ws_ctx: ContextVar[Any]) -> None:
    """Enregistre les outils MCP de gestion des templates de prompts."""

    @mcp.tool()
    async def list_prompt_templates() -> str:
        """Liste la bibliothèque de templates de prompts d'enrichissement.

        Contient les templates système (partagés, lecture seule) et les tiens.
        Un template décrit UN prompt LLM et son point d'application, résumé par
        deux axes : target (document | chunk | region:<type>[:<qualifier>]) et
        timing (post_index_metadata | embedding_inline).

        Pour lier un template à une stratégie de chunking (contexte injecté à
        l'embedding), seuls ceux en timing embedding_inline sont éligibles —
        voir set_chunking_strategy_prompts.

        Sortie : JSON — id, name, language, metadata_key, prompt, target, timing,
        result_type/result_schema, prompt_version, is_system, compteurs d'usage
        (used_by_triggers, used_by_strategies), dates. Lecture seule.
        """
        ctx = ws_ctx.get()
        async with ctx.config_pool.acquire() as conn:
            out = await templates_svc.list_prompt_templates(conn, owner_id=ctx.owner_id)
        return dump(out)

    @mcp.tool()
    async def create_prompt_template(
        name: str,
        language: str,
        metadata_key: str,
        prompt: str,
        mode: str,
        result_type: str = "text",
        description: str | None = None,
        region_type: str | None = None,
        region_qualifier: str | None = None,
    ) -> str:
        """Crée un template de prompt dans ta bibliothèque (niveau admin requis).

        mode — dérive automatiquement les axes (target, timing) :
        - 'document' : métadonnée calculée APRÈS indexation sur le document entier
          (post_index_metadata) ; consultable via get_enrichment, n'altère pas les
          vecteurs. À lier ensuite à un trigger d'extension (IHM) — PAS liable à
          une stratégie de chunking.
        - 'chunk' : contexte injecté dans le texte embeddé de CHAQUE chunk
          (embedding_inline). Liable à une stratégie via
          set_chunking_strategy_prompts.
        - 'region' : injecté uniquement dans les chunks issus d'une région précise
          (embedding_inline). region_type obligatoire ('prose' | 'code_fence' |
          'table' | 'frontmatter' | 'html_block'), region_qualifier
          optionnel (ex. 'mermaid') → target region:<type>[:<qualifier>]. Lier la
          région exige un parser de régions sur la stratégie cible.

        AVERTISSEMENT : les modes chunk/region modifient le texte embeddé donc les
        VECTEURS — une réindexation est nécessaire pour l'existant ; un binding
        n'est jamais actif par défaut (enabled contrôlé au binding).

        Paramètres :
        - name         : nom unique dans ta bibliothèque (max 128).
        - language     : langue/langage visé par le prompt (ex. 'markdown', 'python').
        - metadata_key : clé de rangement du résultat (ex. 'summary', 'context').
        - prompt       : texte du prompt envoyé au LLM.
        - result_type  : 'text' (défaut) ou 'json' (résultat structuré).
        - description  : note libre affichée dans la bibliothèque.

        Sortie : JSON du template créé (avec target/timing dérivés). Erreurs en
        message clair (nom déjà utilisé, mode/région invalides).
        """
        ctx = ws_ctx.get()
        refusal = write_refusal(ctx)
        if refusal:
            return refusal
        try:
            target, timing = _derive_axes(mode, region_type, region_qualifier)
            req = PromptTemplateCreate(
                name=name,
                language=language,
                description=description,
                metadata_key=metadata_key,
                result_type=result_type,
                prompt=prompt,
                target=target,
                timing=timing,
            )
            async with ctx.config_pool.acquire() as conn:
                out = await templates_svc.create_prompt_template(
                    conn, owner_id=ctx.owner_id, req=req
                )
        except EXPECTED_ERRORS as exc:
            return explain(exc)
        log.info("mcp_library.template_created", template_id=str(out.id))
        return dump(out)

    @mcp.tool()
    async def update_prompt_template(
        template_id: str,
        description: str | None = None,
        prompt: str | None = None,
        result_schema: dict[str, Any] | None = None,
    ) -> str:
        """Modifie un de TES templates (niveau admin requis) — les système sont immuables.

        Seuls les champs fournis changent. Modifiables : description, prompt,
        result_schema (schéma JSON attendu si result_type='json'). Figés après
        création : name, language, metadata_key et les axes target/timing — pour
        changer de mode, crée un nouveau template.

        Effet de bord : changer le TEXTE du prompt incrémente prompt_version
        (invalide le cache de contexte) ; pour un template embedding_inline déjà
        lié, une réindexation est nécessaire pour propager le nouveau contexte.
        Sortie : JSON du template à jour, ou message d'erreur explicite.
        """
        ctx = ws_ctx.get()
        refusal = write_refusal(ctx)
        if refusal:
            return refusal
        try:
            req = PromptTemplatePatch(
                description=description, prompt=prompt, result_schema=result_schema
            )
            async with ctx.config_pool.acquire() as conn:
                out = await templates_svc.patch_prompt_template(
                    conn, owner_id=ctx.owner_id, template_id=template_id, req=req
                )
        except EXPECTED_ERRORS as exc:
            return explain(exc)
        return dump(out)

    @mcp.tool()
    async def delete_prompt_template(template_id: str) -> str:
        """Supprime un de TES templates (niveau admin requis).

        Refusé avec le décompte si le template est référencé par des triggers
        d'extension ou des bindings de stratégies — retire ces références d'abord
        (set_chunking_strategy_prompts sans ce template, ou triggers via l'IHM).
        Les templates système ne sont jamais supprimables.
        """
        ctx = ws_ctx.get()
        refusal = write_refusal(ctx)
        if refusal:
            return refusal
        try:
            async with ctx.config_pool.acquire() as conn:
                await templates_svc.delete_prompt_template(
                    conn, owner_id=ctx.owner_id, template_id=template_id
                )
        except EXPECTED_ERRORS as exc:
            return explain(exc)
        return f"Template {template_id} supprimé."
