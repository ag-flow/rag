from __future__ import annotations

from contextvars import ContextVar
from typing import Any

import asyncpg
import structlog
from pydantic import ValidationError

from rag.api.mcp_library_support import dump
from rag.globmatch import glob_match
from rag.schemas.enrichments import TriggerCreate, TriggerPatch
from rag.services import triggers as triggers_svc
from rag.services import workspaces as workspaces_svc
from rag.services.triggers import UnknownTriggerStrategyError

log = structlog.get_logger(__name__)

TRIGGER_ADMIN_REFUSAL = (
    "Accès refusé : la gestion des triggers de chunking exige une clé de "
    "niveau 'admin'."
)
_UNKNOWN_WS = (
    "Workspace '{ws}' introuvable. Appelle list_workspaces() pour les slugs accessibles."
)

_DEFERRED_EFFECT = (
    "Effet différé : les documents déjà indexés conservent leur découpage — "
    "une réindexation est nécessaire pour l'appliquer ({docs} documents déjà "
    "indexés matchent ce pattern)."
)


async def _matching_docs(pool: asyncpg.Pool, ws_id: Any, pattern: str) -> int:
    """Nombre de documents indexés du workspace dont le path matche le pattern."""
    rows = await pool.fetch(
        "SELECT path FROM indexed_documents WHERE workspace_id = $1", ws_id
    )
    return sum(1 for r in rows if glob_match(pattern, r["path"]))


def register_trigger_tools(mcp: Any, ws_ctx: ContextVar[Any]) -> None:
    """Outils MCP des triggers de sélection de stratégie de chunking.

    Un trigger lie un PATTERN GLOB de chemin (`backlog/**/*.md`) à une
    stratégie de chunking dans un workspace. Mêmes services et mêmes gardes
    que l'IHM (visibilité de la stratégie, unicité du pattern).
    """

    async def _owned_ws_id(ctx: Any, workspace: str) -> object | None:
        async with ctx.config_pool.acquire() as conn:
            return await workspaces_svc.resolve_owned_workspace_id(
                conn, name=workspace, owner_id=ctx.owner_id
            )

    @mcp.tool()
    async def list_chunking_triggers(workspace: str) -> str:
        """Triggers de chunking d'un workspace (pattern glob → stratégie).

        - workspace : slug du workspace (voir list_workspaces)

        Sortie : JSON [{id, pattern, enabled, strategy_id, created_at}].

        Ordre de résolution du découpage d'un fichier : surcharge explicite
        du push > trigger de pattern > cascade extension→catégorie > stratégie
        par défaut du workspace. Entre triggers concurrents, le pattern le plus
        spécifique gagne : plus de segments (`/`), puis pattern le plus long,
        puis le plus ancien.

        Lecture seule, toute clé valide.
        """
        ctx = ws_ctx.get()
        if await _owned_ws_id(ctx, workspace) is None:
            return _UNKNOWN_WS.format(ws=workspace)
        async with ctx.config_pool.acquire() as conn:
            triggers = await triggers_svc.list_triggers(conn, workspace_name=workspace)
        return dump(triggers)

    @mcp.tool()
    async def create_chunking_trigger(
        workspace: str,
        pattern: str,
        strategy_id: str | None = None,
        enabled: bool = True,
    ) -> str:
        """Crée un trigger : pattern glob de chemin → stratégie de chunking.

        - workspace   : slug du workspace (voir list_workspaces)
        - pattern     : glob sur le chemin complet — `*` = un segment, `**` =
          toute profondeur (ex. `backlog/**/*.md`, `datasets/*.csv`). Unique
          par workspace.
        - strategy_id : id d'une stratégie visible du caller
          (list_chunking_strategies) ; omis = trigger créé sans binding (les
          prompts d'enrichissement du trigger restent pilotés par l'IHM)
        - enabled     : actif dès la création (défaut true)

        Ordre de résolution du découpage d'un fichier : surcharge explicite
        du push > trigger de pattern > cascade extension→catégorie > stratégie
        par défaut du workspace. Entre triggers concurrents, le pattern le plus
        spécifique gagne : plus de segments (`/`), puis pattern le plus long,
        puis le plus ancien.

        Requiert une clé 'admin'. Sortie : JSON du trigger créé + nombre de
        documents déjà indexés concernés (réindexation nécessaire pour eux).
        """
        ctx = ws_ctx.get()
        if ctx.scope != "admin":
            return TRIGGER_ADMIN_REFUSAL
        ws_id = await _owned_ws_id(ctx, workspace)
        if ws_id is None:
            return _UNKNOWN_WS.format(ws=workspace)
        try:
            req = TriggerCreate(
                pattern=pattern,
                enabled=enabled,
                strategy_id=strategy_id,  # type: ignore[arg-type]
            )
        except ValidationError as exc:
            return f"Paramètres invalides : {exc}"
        try:
            async with ctx.config_pool.acquire() as conn:
                trigger = await triggers_svc.create_trigger(
                    conn, workspace_name=workspace, req=req, owner_id=ctx.owner_id
                )
        except UnknownTriggerStrategyError as exc:
            return (
                f"{exc} — elle n'existe pas ou n'est pas visible depuis ta "
                "bibliothèque (list_chunking_strategies)."
            )
        except asyncpg.UniqueViolationError:
            return (
                f"Un trigger avec le pattern '{req.pattern}' existe déjà dans "
                f"'{workspace}' (list_chunking_triggers)."
            )
        docs = await _matching_docs(ctx.config_pool, ws_id, req.pattern)
        log.info("mcp.trigger_created", workspace=workspace, pattern=req.pattern)
        return dump(
            {
                "trigger": trigger,
                "matching_indexed_documents": docs,
                "note": _DEFERRED_EFFECT.format(docs=docs),
            }
        )

    @mcp.tool()
    async def update_chunking_trigger(
        workspace: str,
        trigger_id: str,
        enabled: bool | None = None,
        strategy_id: str | None = None,
        clear_strategy: bool = False,
    ) -> str:
        """Modifie un trigger de chunking (activation et/ou stratégie liée).

        - workspace      : slug du workspace
        - trigger_id     : id du trigger (list_chunking_triggers)
        - enabled        : activer/désactiver (omis = inchangé)
        - strategy_id    : nouvelle stratégie liée (omis = inchangée)
        - clear_strategy : true retire le binding (retour cascade/défaut)

        Le pattern d'un trigger est immuable : supprimer puis recréer pour en
        changer. Requiert une clé 'admin'. Sortie : JSON du trigger + nombre
        de documents indexés concernés (réindexation nécessaire pour eux).
        """
        ctx = ws_ctx.get()
        if ctx.scope != "admin":
            return TRIGGER_ADMIN_REFUSAL
        ws_id = await _owned_ws_id(ctx, workspace)
        if ws_id is None:
            return _UNKNOWN_WS.format(ws=workspace)
        if clear_strategy and strategy_id is not None:
            return "Paramètres invalides : strategy_id et clear_strategy sont exclusifs."
        try:
            fields: dict[str, Any] = {}
            if enabled is not None:
                fields["enabled"] = enabled
            if clear_strategy:
                fields["strategy_id"] = None
            elif strategy_id is not None:
                fields["strategy_id"] = strategy_id
            req = TriggerPatch(**fields)
        except ValidationError as exc:
            return f"Paramètres invalides : {exc}"
        try:
            async with ctx.config_pool.acquire() as conn:
                trigger = await triggers_svc.patch_trigger(
                    conn,
                    workspace_name=workspace,
                    trigger_id=trigger_id,
                    req=req,
                    owner_id=ctx.owner_id,
                )
        except UnknownTriggerStrategyError as exc:
            return (
                f"{exc} — elle n'existe pas ou n'est pas visible depuis ta "
                "bibliothèque (list_chunking_strategies)."
            )
        if trigger is None:
            return f"Trigger '{trigger_id}' introuvable dans '{workspace}'."
        docs = await _matching_docs(ctx.config_pool, ws_id, trigger.pattern)
        log.info("mcp.trigger_updated", workspace=workspace, trigger=trigger_id)
        return dump(
            {
                "trigger": trigger,
                "matching_indexed_documents": docs,
                "note": _DEFERRED_EFFECT.format(docs=docs),
            }
        )

    @mcp.tool()
    async def delete_chunking_trigger(workspace: str, trigger_id: str) -> str:
        """Supprime un trigger de chunking (et ses bindings de prompts).

        - workspace  : slug du workspace
        - trigger_id : id du trigger (list_chunking_triggers)

        Les fichiers qui matchaient retombent sur la cascade
        extension→catégorie puis le défaut du workspace. Effet différé : les
        documents déjà indexés conservent leur découpage jusqu'à réindexation.
        Requiert une clé 'admin'.
        """
        ctx = ws_ctx.get()
        if ctx.scope != "admin":
            return TRIGGER_ADMIN_REFUSAL
        if await _owned_ws_id(ctx, workspace) is None:
            return _UNKNOWN_WS.format(ws=workspace)
        async with ctx.config_pool.acquire() as conn:
            deleted = await triggers_svc.delete_trigger(
                conn, workspace_name=workspace, trigger_id=trigger_id
            )
        if not deleted:
            return f"Trigger '{trigger_id}' introuvable dans '{workspace}'."
        log.info("mcp.trigger_deleted", workspace=workspace, trigger=trigger_id)
        return f"Trigger supprimé de '{workspace}'."
