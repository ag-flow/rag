"""Cycle de vie d'un workspace partagé par les surfaces clé API (REST, MCP).

Point d'application unique pour ce que les surfaces faisaient chacune de leur
côté : trouver un endpoint par coffre + slug, émettre `workspace_created`, et
cibler un workspace POSSÉDÉ pour le supprimer. Une garde dupliquée finit par
diverger (leçon OBO REST/MCP, 2026-09-05).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from rag.api.errors import AdminError, WorkspaceNotFound
from rag.events import emit as events_emit
from rag.events.registry import workspace_created
from rag.schemas.admin import WorkspaceCreateResolved
from rag.schemas.vault_endpoints import EndpointOut
from rag.services import vault_endpoints as endpoints_svc


class VaultNotVisible(AdminError):
    """Coffre inexistant ou invisible pour l'appelant — indistinguables à
    dessein : révéler l'existence du coffre d'autrui serait une fuite."""

    http_status = 404

    def __init__(self, vault: str) -> None:
        super().__init__(vault)
        self.vault = vault

    def to_payload(self) -> dict[str, object]:
        return {"error": "vault_not_found", "vault": self.vault}


class EndpointNotInVault(AdminError):
    http_status = 404

    def __init__(self, vault: str, endpoint: str) -> None:
        super().__init__(vault, endpoint)
        self.vault = vault
        self.endpoint = endpoint

    def to_payload(self) -> dict[str, object]:
        return {"error": "endpoint_not_found", "vault": self.vault, "endpoint": self.endpoint}


_VISIBLE_VAULT_SQL = (
    "SELECT id FROM harpocrate_vaults WHERE (is_default = true OR owner_id = $1) AND name = $2"
)

# Workspace supprimable par une clé : POSSÉDÉ par son porteur, jamais partagé
# (owner NULL). Un workspace partagé sert tout le monde : une clé utilisateur ne
# doit pas pouvoir le détruire, quel que soit son scope.
_OWNED_WS_SQL = "SELECT id FROM workspaces WHERE name = $1 AND owner_id = $2"


async def resolve_endpoint_by_slug(
    conn: asyncpg.Connection, *, owner_id: str, vault: str, endpoint: str
) -> EndpointOut:
    """Endpoint visible (coffre par défaut ou possédé) désigné par coffre + slug."""
    vault_row = await conn.fetchrow(_VISIBLE_VAULT_SQL, owner_id, vault)
    if vault_row is None:
        raise VaultNotVisible(vault)
    endpoints = await endpoints_svc.list_endpoints(conn, vault_id=vault_row["id"])
    found = next((e for e in endpoints if e.slug == endpoint), None)
    if found is None:
        raise EndpointNotInVault(vault, endpoint)
    return found


async def resolve_owned_workspace_for_deletion(
    conn: asyncpg.Connection, *, owner_id: str, workspace: str
) -> UUID:
    """Id du workspace possédé par `owner_id`. Inexistant, partagé ou d'autrui →
    même 404 : ne pas révéler l'existence d'un workspace qu'on ne peut toucher."""
    row = await conn.fetchrow(_OWNED_WS_SQL, workspace, owner_id)
    if row is None:
        raise WorkspaceNotFound(workspace)
    workspace_id: UUID = row["id"]
    return workspace_id


async def emit_workspace_created(pool: asyncpg.Pool, resolved: WorkspaceCreateResolved) -> None:
    """Event workflow APRÈS le succès de la création (fire-and-forget, ne lève pas)."""
    await events_emit.emit_workflow_event(
        pool,
        workspace_created(
            name=resolved.name,
            label=resolved.label,
            slug=resolved.name,
            owner_id=resolved.owner_id,
            occurred_at=datetime.now(UTC),
        ),
    )
