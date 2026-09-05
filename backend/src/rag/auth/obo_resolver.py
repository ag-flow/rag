"""Owner effectif d'un appel porteur de clé API — point d'application UNIQUE de l'OBO.

Le contrat OBO (d0e2dad3 v6, cf. `rag.auth.obo`) dit *comment* vérifier une
identité humaine signée ; ce module dit *qui* est le propriétaire attribué à
l'appel, et il est partagé par les DEUX surfaces du service :

- MCP   : middleware de `rag.api.mcp_standard` ;
- REST  : `require_apikey_owner` de `rag.auth.workspace_auth`.

Les faire diverger attribuait deux `owner_id` distincts au même humain porteur
de la même clé : un workspace créé via MCP appartenait à l'humain, tandis que
le push REST se présentait au nom de la clé — 401 sur son propre workspace.

Fail-safe du contrat : une identité absente, mal signée ou inconnue n'est
JAMAIS une erreur — on retombe sur l'identité de la clé. Chaque branche est
journalisée, faute de quoi le choix d'attribution reste indiagnosticable.
"""

from __future__ import annotations

import asyncpg
import structlog

from rag.auth.obo import ACTOR_HEADER, SIGNATURE_HEADER, TIMESTAMP_HEADER, read_obo_actor
from rag.auth.owner import principal_to_owner_id
from rag.services.user_profile import email_for_identity

log = structlog.get_logger(__name__)

_OBO_HEADERS = frozenset({ACTOR_HEADER, TIMESTAMP_HEADER, SIGNATURE_HEADER})


def _obo_headers_present(headers: list[tuple[bytes, bytes]]) -> tuple[bool, bool]:
    """(au moins un en-tête OBO, les trois en-têtes OBO)."""
    names = {name.lower() for name, _ in headers} & _OBO_HEADERS
    return bool(names), len(names) == len(_OBO_HEADERS)


async def resolve_effective_owner_id(
    config_pool: asyncpg.Pool,
    headers: list[tuple[bytes, bytes]],
    api_key: str,
    *,
    key_owner_id: str,
    surface: str,
    now: float | None = None,
) -> str:
    """`owner_id` à porter par cet appel : l'humain si l'OBO résout, sinon la clé.

    `headers` est la liste brute ASGI (`scope["headers"]` ou `request.headers.raw`),
    `api_key` le Bearer de CETTE requête — il est le secret de signature du
    contrat. `surface` ("mcp" / "rest") n'a qu'une valeur de journalisation.
    """
    any_header, all_headers = _obo_headers_present(headers)
    if not any_header:
        log.debug("obo.absent", surface=surface, owner=key_owner_id[:8])
        return key_owner_id
    if not all_headers:
        log.warning("obo.incomplete_headers", surface=surface, owner=key_owner_id[:8])
        return key_owner_id

    actor = read_obo_actor(headers, api_key, now=now)
    if actor is None:
        log.warning("obo.invalid_signature", surface=surface, owner=key_owner_id[:8])
        return key_owner_id

    email = await email_for_identity(config_pool, actor)
    if email is None:
        log.warning("obo.unknown_identity", surface=surface, actor=actor[:8])
        return key_owner_id

    owner_id = principal_to_owner_id(email)
    log.debug("obo.resolved", surface=surface, actor=actor[:8], owner=owner_id[:8])
    return owner_id
