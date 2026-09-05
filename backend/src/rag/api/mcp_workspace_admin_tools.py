from __future__ import annotations

from contextvars import ContextVar
from typing import Any
from uuid import UUID

import structlog
from pydantic import ValidationError

from rag.api.errors import AdminError, ChunkingChangeRequiresReindex, IndexerChangeRequiresReindex
from rag.api.mcp_library_support import dump, parse_uuid
from rag.services import workspaces as workspaces_svc

log = structlog.get_logger(__name__)

WORKSPACE_ADMIN_REFUSAL = (
    "Accès refusé : l'administration des workspaces (création, reset, binding "
    "de stratégie) exige une clé de niveau 'admin'."
)
_UNKNOWN_WS = (
    "Workspace '{ws}' introuvable. Appelle list_workspaces() pour les slugs accessibles."
)


def register_workspace_admin_tools(mcp: Any, ws_ctx: ContextVar[Any]) -> None:
    """Outils MCP d'administration des workspaces RAG.

    Tout exige scope admin. La création copie la config de l'endpoint choisi
    (snapshot) et provisionne la base pgvector dédiée ; le reset recopie la
    config depuis l'endpoint d'origine ; le défaut de chunking est lié PAR ID
    vers une stratégie visible du caller. Mêmes services que l'API REST.
    """

    def _refusal(ctx: Any) -> str | None:
        return None if ctx.scope == "admin" else WORKSPACE_ADMIN_REFUSAL

    async def _owned_ws_id(ctx: Any, workspace: str) -> object | None:
        async with ctx.config_pool.acquire() as conn:
            return await workspaces_svc.resolve_owned_workspace_id(
                conn, name=workspace, owner_id=ctx.owner_id
            )

    @mcp.tool()
    async def create_workspace(
        name: str,
        vault: str,
        endpoint: str,
        label: str | None = None,
        description: str = "",
    ) -> str:
        """Crée un workspace RAG rattaché à un endpoint (préréglage de coffre).

        - name        : slug du workspace (minuscules, chiffres, tirets — max 63)
        - vault       : nom du coffre Harpocrate portant l'endpoint (list_endpoints)
        - endpoint    : slug de l'endpoint dont la config est copiée (snapshot)
        - label       : libellé d'affichage (défaut : name)
        - description : description libre

        La config vectorisation/rerank/LLM de l'endpoint est COPIÉE : les
        modifications ultérieures de l'endpoint n'affectent pas ce workspace
        (voir reset_workspace_from_endpoint pour resynchroniser). Une base
        pgvector dédiée est provisionnée. Le workspace appartient au porteur
        de la clé. Requiert une clé 'admin'.

        Sortie : JSON {name, label, ...} du workspace créé, ou message d'erreur
        explicite (slug pris, endpoint introuvable, ref de clé invalide…).
        """
        from rag.services.workspaces import create_workspace as create_ws
        from rag.services.workspaces import resolved_from_endpoint

        ctx = ws_ctx.get()
        refusal = _refusal(ctx)
        if refusal:
            return refusal
        if ctx.admin_dsn is None or ctx.vaults_service is None:
            return "Service indisponible : administration des workspaces non initialisée."

        ep = await _find_endpoint(ctx, vault, endpoint)
        if isinstance(ep, str):
            return ep
        try:
            resolved = resolved_from_endpoint(
                name=name,
                label=label or name,
                description=description,
                owner_id=ctx.owner_id,
                endpoint=ep,
            )
        except ValidationError as exc:
            return f"Paramètres invalides : {exc}"
        try:
            resp = await create_ws(
                request=resolved,
                config_pool=ctx.config_pool,
                admin_dsn=ctx.admin_dsn,
                resolver=ctx.resolver,
                harpocrate_vaults_service=ctx.vaults_service,
            )
        except AdminError as exc:
            return f"Création refusée : {dump(exc.to_payload())}"

        await _emit_created(ctx, resolved)
        log.info(
            "mcp.workspace_created",
            workspace=name,
            owner=ctx.owner_id[:8],
            owner_source=getattr(ctx, "owner_source", "apikey"),
        )
        return dump(resp)

    @mcp.tool()
    async def reset_workspace_from_endpoint(workspace: str, confirm: bool = False) -> str:
        """Réinitialise la config d'un workspace depuis son endpoint d'origine.

        Recopie vectorisation, rerank et LLM depuis l'endpoint lié à la
        création (le workspace ne change pas d'endpoint) :
        - clé/base_url/limites seuls modifiés → mise à jour directe ;
        - provider/modèle d'embedding modifiés → RE-VECTORISATION complète :
          refus explicite sans confirm=true (le nombre de documents concernés
          est indiqué), job de reindex sinon ;
        - rerank/LLM retirés de l'endpoint → retirés du workspace.

        Requiert une clé 'admin'. Sortie : JSON {indexer, rerank, llm, job}
        (unchanged | updated | reindex_triggered | removed | none).
        """
        from rag.services.endpoint_refresh import (
            DefaultVaultMissingError,
            EndpointGoneError,
            NoEndpointLinkedError,
            refresh_workspace_from_endpoint,
        )

        ctx = ws_ctx.get()
        refusal = _refusal(ctx)
        if refusal:
            return refusal
        if ctx.admin_dsn is None:
            return "Service indisponible : administration des workspaces non initialisée."
        ws_id = await _owned_ws_id(ctx, workspace)
        if ws_id is None:
            return _UNKNOWN_WS.format(ws=workspace)
        try:
            result = await refresh_workspace_from_endpoint(
                workspace_id=ws_id,  # type: ignore[arg-type]
                workspace_name=workspace,
                confirm=confirm,
                config_pool=ctx.config_pool,
                admin_dsn=ctx.admin_dsn,
                resolver=ctx.resolver,
                default_vault_name=ctx.default_vault_name,
            )
        except NoEndpointLinkedError:
            return (
                f"Le workspace '{workspace}' n'est lié à aucun endpoint (créé avant "
                "le lien endpoint) : rien à recopier. Recrée-le depuis un endpoint."
            )
        except EndpointGoneError:
            return (
                f"L'endpoint d'origine du workspace '{workspace}' a été supprimé : "
                "reset impossible."
            )
        except DefaultVaultMissingError:
            return "Aucun coffre Harpocrate par défaut configuré : reset impossible."
        except IndexerChangeRequiresReindex as exc:
            return (
                f"Le modèle d'embedding change ({exc.current} → {exc.requested}) : "
                f"{exc.documents_count} documents seront RE-VECTORISÉS. Relance avec "
                "confirm=true pour déclencher la réindexation."
            )
        log.info("mcp.workspace_reset", workspace=workspace, owner=ctx.owner_id[:8])
        return dump(result)

    @mcp.tool()
    async def set_default_chunking_strategy(
        workspace: str, strategy_id: str | None = None, confirm: bool = False
    ) -> str:
        """Définit la stratégie de chunking PAR DÉFAUT d'un workspace (lien par id).

        Ordre de résolution du découpage d'un fichier : surcharge explicite du
        push > trigger de pattern (le plus spécifique gagne) > cascade
        extension→catégorie > CE DÉFAUT. `strategy_id=null` retire le binding
        (retour à la cascade textuelle).

        Effet différé : les documents déjà indexés conservent leur découpage.
        Si le workspace contient des documents, le changement exige
        confirm=true et déclenche un job de réindexation (le nombre de
        documents concernés est indiqué). Requiert une clé 'admin' ; la
        stratégie doit être visible du caller (système ou sa bibliothèque —
        list_chunking_strategies).

        Sortie : JSON du résultat (updated | reindex_triggered + job) ou
        message explicite (no_change, stratégie invisible, confirmation requise).
        """
        from rag.services.jobs import UnknownDefaultStrategyError, apply_default_strategy_change

        ctx = ws_ctx.get()
        refusal = _refusal(ctx)
        if refusal:
            return refusal
        ws_id = await _owned_ws_id(ctx, workspace)
        if ws_id is None:
            return _UNKNOWN_WS.format(ws=workspace)
        sid: UUID | None = None
        if strategy_id is not None:
            try:
                sid = parse_uuid(strategy_id)
            except ValueError as exc:
                return str(exc)
        try:
            result = await apply_default_strategy_change(
                name=workspace,
                strategy_id=sid,
                owner_id=ctx.owner_id,
                confirm=confirm,
                config_pool=ctx.config_pool,
            )
        except UnknownDefaultStrategyError as exc:
            return (
                f"{exc} — elle n'existe pas ou n'est pas visible depuis ta "
                "bibliothèque (list_chunking_strategies)."
            )
        except ChunkingChangeRequiresReindex:
            docs = await ctx.config_pool.fetchval(
                "SELECT COUNT(*) FROM indexed_documents WHERE workspace_id = $1", ws_id
            )
            return (
                f"Le workspace contient {int(docs or 0)} documents indexés dont le "
                "découpage changerait. Relance avec confirm=true pour appliquer et "
                "déclencher la réindexation."
            )
        if result == "no_change":
            return "Aucun changement : cette stratégie est déjà le défaut du workspace."
        tag, body = result
        log.info("mcp.default_strategy_set", workspace=workspace, mode=tag)
        return dump({"status": tag, **body})


async def _find_endpoint(ctx: Any, vault: str, endpoint: str) -> Any:
    """Endpoint visible par vault+slug, ou message d'erreur pédagogique (str)."""
    from rag.services import vault_endpoints as endpoints_svc

    async with ctx.config_pool.acquire() as conn:
        v = await conn.fetchrow(
            "SELECT id, owner_id FROM harpocrate_vaults "
            "WHERE (is_default = true OR owner_id = $1) AND name = $2",
            ctx.owner_id,
            vault,
        )
        if v is None:
            return (
                f"Coffre '{vault}' introuvable ou invisible. Appelle list_endpoints() "
                "pour les coffres accessibles."
            )
        eps = await endpoints_svc.list_endpoints(conn, vault_id=v["id"])
    ep = next((e for e in eps if e.slug == endpoint), None)
    if ep is None:
        return (
            f"Endpoint '{endpoint}' introuvable dans le coffre '{vault}'. "
            "Appelle list_endpoints() pour les slugs disponibles."
        )
    return ep


async def _emit_created(ctx: Any, resolved: Any) -> None:
    """Émet l'event workflow APRÈS le succès (fire-and-forget, parité REST)."""
    from datetime import UTC, datetime

    from rag.events.emit import emit_workflow_event
    from rag.events.registry import workspace_created

    await emit_workflow_event(
        ctx.config_pool,
        workspace_created(
            name=resolved.name,
            label=resolved.label,
            slug=resolved.name,
            owner_id=resolved.owner_id,
            occurred_at=datetime.now(UTC),
        ),
    )
