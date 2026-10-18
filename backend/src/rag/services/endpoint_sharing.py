"""Visibilité et partage des endpoints de coffre (migration 095, epic f3cc98a8).

Un endpoint est UTILISABLE (création de workspace, rafraîchissement) par un
appelant si l'une de ces conditions tient :
  - son coffre est visible de l'appelant (coffre par défaut, ou possédé) ;
  - il est partagé avec tout le monde (`shared_with_all`) ;
  - il est partagé avec l'appelant, nommément (`vault_endpoint_shares`).

Cette règle est écrite UNE fois (`_ACCESS_SQL`) et sert à toutes les surfaces
(IHM, REST clé API, MCP) : la dupliquer ferait diverger ce qu'un même
utilisateur voit selon le chemin, comme l'OBO l'a montré (LESSONS, 2026-09-05).

L'appelant est désigné par son `owner_id` effectif (session, clé API, ou humain
OBO). Le partage nominatif vise un `users.id` et mémorise son `owner_id`,
calculé ICI par `principal_to_owner_id` — jamais recalculé en SQL, dont le
lower() ne replie pas l'Unicode comme Python.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import asyncpg
import structlog

from rag.auth.owner import principal_to_owner_id
from rag.schemas.endpoint_sharing import EndpointSharingOut, EndpointSharingUpdate, ShareUser

log = structlog.get_logger(__name__)


class UnknownShareUserError(ValueError):
    """Un bénéficiaire demandé n'existe pas dans `users`."""


# Accès d'un appelant ($1 = owner_id) à chaque endpoint : 'owned' | 'default' |
# 'shared', ligne absente si aucun. La possession prime (seul le propriétaire
# écrit) ; le partage n'est retenu qu'à défaut de visibilité par le coffre.
# Filtres optionnels : $2 = id d'endpoint, $3/$4 = nom de coffre + slug.
_ACCESS_SQL = """
    SELECT * FROM (
        SELECT e.id, e.slug, e.label,
               e.indexer_provider, e.indexer_model,
               e.rerank_provider, e.rerank_model,
               e.llm_provider, e.llm_model,
               v.id AS vault_id, v.name AS vault_name, v.label AS vault_label,
               CASE
                   WHEN v.owner_id = $1 THEN 'owned'
                   WHEN v.is_default THEN 'default'
                   WHEN e.shared_with_all THEN 'shared'
                   WHEN EXISTS (
                       SELECT 1 FROM vault_endpoint_shares s
                       WHERE s.endpoint_id = e.id AND s.owner_id = $1
                   ) THEN 'shared'
               END AS access
        FROM vault_endpoints e
        JOIN harpocrate_vaults v ON v.id = e.vault_id
        WHERE ($2::uuid IS NULL OR e.id = $2)
          AND ($3::text IS NULL OR (v.name = $3 AND e.slug = $4))
    ) a
    WHERE a.access IS NOT NULL
    ORDER BY a.vault_label, a.label
"""


@dataclass(frozen=True)
class UsableEndpoint:
    """Endpoint utilisable par l'appelant, SANS références de secrets ni repli.

    C'est tout ce qu'un bénéficiaire de partage a le droit de voir : de quoi
    choisir l'endpoint, pas de quoi reconstituer sa configuration.
    """

    id: UUID
    slug: str
    label: str
    vault_id: UUID
    vault_name: str
    vault_label: str
    access: Literal["owned", "default", "shared"]
    indexer: tuple[str, str]
    rerank: tuple[str, str] | None
    llm: tuple[str, str] | None


def _to_usable(row: asyncpg.Record) -> UsableEndpoint:
    def pair(prefix: str) -> tuple[str, str] | None:
        provider = row[f"{prefix}_provider"]
        return None if provider is None else (provider, row[f"{prefix}_model"])

    return UsableEndpoint(
        id=row["id"],
        slug=row["slug"],
        label=row["label"],
        vault_id=row["vault_id"],
        vault_name=row["vault_name"],
        vault_label=row["vault_label"],
        access=row["access"],
        indexer=(row["indexer_provider"], row["indexer_model"]),
        rerank=pair("rerank"),
        llm=pair("llm"),
    )


async def db_list_usable_endpoints(
    conn: asyncpg.Connection, *, owner_id: str
) -> list[UsableEndpoint]:
    """Tous les endpoints que l'appelant peut utiliser, triés coffre puis label."""
    rows = await conn.fetch(_ACCESS_SQL, owner_id, None, None, None)
    return [_to_usable(r) for r in rows]


async def db_get_usable_endpoint(
    conn: asyncpg.Connection, *, owner_id: str, endpoint_id: UUID
) -> UsableEndpoint | None:
    """L'endpoint s'il est utilisable par l'appelant ; None s'il n'existe pas OU
    n'est pas utilisable — indistinction voulue, comme pour les workspaces."""
    row = await conn.fetchrow(_ACCESS_SQL, owner_id, endpoint_id, None, None)
    return None if row is None else _to_usable(row)


async def db_find_usable_endpoint_by_slug(
    conn: asyncpg.Connection, *, owner_id: str, vault: str, endpoint: str
) -> UsableEndpoint | None:
    """Endpoint utilisable désigné par nom de coffre + slug (surfaces clé API)."""
    row = await conn.fetchrow(_ACCESS_SQL, owner_id, None, vault, endpoint)
    return None if row is None else _to_usable(row)


_SHARES_SQL = """
    SELECT u.id, u.username, u.email
    FROM vault_endpoint_shares s JOIN users u ON u.id = s.user_id
    WHERE s.endpoint_id = $1
    ORDER BY u.email
"""


async def db_get_sharing(conn: asyncpg.Connection, *, endpoint_id: UUID) -> EndpointSharingOut:
    """État de partage d'un endpoint (lecture propriétaire)."""
    shared_with_all = await conn.fetchval(
        "SELECT shared_with_all FROM vault_endpoints WHERE id = $1", endpoint_id
    )
    if shared_with_all is None:
        raise LookupError(str(endpoint_id))
    rows = await conn.fetch(_SHARES_SQL, endpoint_id)
    return EndpointSharingOut(
        shared_with_all=shared_with_all,
        users=[ShareUser(id=r["id"], username=r["username"], email=r["email"]) for r in rows],
    )


async def db_set_sharing(
    conn: asyncpg.Connection, *, endpoint_id: UUID, req: EndpointSharingUpdate
) -> EndpointSharingOut:
    """Remplace l'état de partage en UNE transaction (flag + liste complète).

    Remplacement intégral plutôt qu'ajout/retrait unitaire : l'IHM envoie l'état
    voulu, et une liste partiellement appliquée laisserait un partage que
    personne n'a demandé. Un utilisateur inconnu fait tout échouer.
    """
    async with conn.transaction():
        updated = await conn.execute(
            "UPDATE vault_endpoints SET shared_with_all = $2, updated_at = now() WHERE id = $1",
            endpoint_id,
            req.shared_with_all,
        )
        if updated == "UPDATE 0":
            raise LookupError(str(endpoint_id))
        await conn.execute("DELETE FROM vault_endpoint_shares WHERE endpoint_id = $1", endpoint_id)
        user_ids = list(dict.fromkeys(req.user_ids))
        if user_ids:
            # FOR SHARE : le compte ne peut disparaître entre sa lecture et
            # l'INSERT — sinon un owner_id survivrait à son utilisateur.
            users = await conn.fetch(
                "SELECT id, email FROM users WHERE id = ANY($1::uuid[]) FOR SHARE", user_ids
            )
            if len(users) != len(user_ids):
                raise UnknownShareUserError(str(endpoint_id))
            await conn.executemany(
                "INSERT INTO vault_endpoint_shares (endpoint_id, user_id, owner_id) "
                "VALUES ($1, $2, $3)",
                [(endpoint_id, u["id"], principal_to_owner_id(u["email"])) for u in users],
            )
    log.info(
        "endpoint.sharing_updated",
        endpoint=str(endpoint_id),
        shared_with_all=req.shared_with_all,
        users=len(user_ids),
    )
    return await db_get_sharing(conn, endpoint_id=endpoint_id)


async def db_find_share_candidate(conn: asyncpg.Connection, *, email: str) -> ShareUser | None:
    """Utilisateur existant désigné par son email EXACT (casse ignorée), sinon None.

    Décision architecte (2026-10-18) : on ne liste jamais l'annuaire — il
    exposerait l'email de tous les comptes à tout utilisateur de l'IHM. Qui
    partage doit déjà connaître l'adresse du bénéficiaire.
    """
    row = await conn.fetchrow(
        "SELECT id, username, email FROM users WHERE lower(email) = lower($1)", email
    )
    return (
        None
        if row is None
        else ShareUser(id=row["id"], username=row["username"], email=row["email"])
    )
