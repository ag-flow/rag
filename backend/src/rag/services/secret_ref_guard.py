"""Garde des références de secrets écrites dans une config de service de workspace.

Une config de service (vectorisation, rerank, LLM) associe une référence de
secret (`${vault://<coffre>:<chemin>}`) à un `base_url`. Qui peut écrire l'une
sans contrôler l'autre peut faire envoyer la clé d'un coffre vers son propre
serveur. Règle (décision architecte 2026-10-18) : un appelant n'écrit dans une
config QUE des références vers un coffre qu'il peut modifier — possédé, ou
coffre par défaut, lui-même modifiable par tout admin (`_check_vault_access`) :
le verrouiller n'ôterait rien, son endpoint restant éditable par tous.

Hors de cette garde, et c'est voulu : la création de workspace et « Rafraîchir
depuis l'endpoint », dont les références viennent d'un endpoint UTILISABLE
(`rag.services.endpoint_sharing`) — c'est le seul chemin d'un bénéficiaire de
partage vers les clés du propriétaire, et il ne lui laisse pas choisir l'URL.
"""

from __future__ import annotations

import asyncpg
import structlog

from rag.secrets.refs import as_vault_ref, parse_ref

log = structlog.get_logger(__name__)


class ForeignVaultRefError(Exception):
    """La référence vise un coffre que l'appelant ne peut pas modifier."""

    def __init__(self, vault: str) -> None:
        super().__init__(vault)
        self.vault = vault


_WRITABLE_VAULT_SQL = (
    "SELECT 1 FROM harpocrate_vaults WHERE name = $1 AND (is_default OR owner_id = $2)"
)


async def db_require_writable_vault_refs(
    conn: asyncpg.Connection,
    *,
    owner_id: str,
    refs: list[str | None],
    default_vault_name: str,
) -> None:
    """Lève `ForeignVaultRefError` si une référence vise un coffre non modifiable.

    Une clé logique nue se résout dans le coffre par défaut (même normalisation
    que la résolution réelle, `as_vault_ref`). Un coffre inconnu est refusé :
    fail closed, on ne laisse pas passer ce qu'on ne sait pas attribuer.
    """
    for ref in refs:
        if not ref:
            continue
        try:
            vault, _path = parse_ref(as_vault_ref(ref, default_vault_name))
        except ValueError as exc:
            # Référence malformée : pas de coffre attribuable, donc refusée.
            raise ForeignVaultRefError("<invalid>") from exc
        if await conn.fetchval(_WRITABLE_VAULT_SQL, vault, owner_id) is None:
            log.warning("workspace.secret_ref_refused", vault=vault, owner=owner_id[:8])
            raise ForeignVaultRefError(vault)
