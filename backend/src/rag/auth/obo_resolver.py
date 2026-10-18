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
pas une erreur — on retombe sur l'identité de la clé. SAUF pour une clé
marquée `require_obo` (migration 094) : le propriétaire a alors exigé qu'un
humain identifié accompagne chaque appel, et le repli devient un refus.
Chaque branche est journalisée, faute de quoi la décision reste
indiagnosticable.
"""

from __future__ import annotations

from hashlib import sha256

import asyncpg
import structlog

from rag.auth.obo import ACTOR_HEADER, SIGNATURE_HEADER, TIMESTAMP_HEADER, read_obo_actor
from rag.auth.owner import principal_to_owner_id
from rag.services.user_profile import email_for_identity

log = structlog.get_logger(__name__)

_OBO_HEADERS = frozenset({ACTOR_HEADER, TIMESTAMP_HEADER, SIGNATURE_HEADER})


class OboRequiredError(Exception):
    """La clé exige une identité OBO et l'appel n'en porte pas de valide.

    `reason` ∈ {absent, incomplete_headers, invalid_signature, unknown_identity} :
    journalisée seulement — la réponse HTTP reste un 401 `obo_required` unique,
    pour ne pas guider un appelant dans la forge des en-têtes.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


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
    require_obo: bool = False,
    now: float | None = None,
) -> str:
    """`owner_id` à porter par cet appel : l'humain si l'OBO résout, sinon la clé.

    `headers` est la liste brute ASGI (`scope["headers"]` ou `request.headers.raw`),
    `api_key` le Bearer de CETTE requête — il est le secret de signature du
    contrat. `surface` ("mcp" / "rest" / "search") n'a qu'une valeur de
    journalisation. Lève `OboRequiredError` si `require_obo` et que l'OBO ne
    résout pas.
    """
    owner_id, reason = await _resolve_obo_owner(
        config_pool, headers, api_key, key_owner_id=key_owner_id, surface=surface, now=now
    )
    if owner_id is not None:
        return owner_id
    if require_obo:
        # Fail closed, voulu par le propriétaire de la clé : sans humain signé
        # et connu, l'appel ne doit PAS retomber sur l'identité de la clé —
        # c'est précisément le repli que le flag interdit.
        log.warning("obo.required_refused", surface=surface, reason=reason, owner=key_owner_id[:8])
        raise OboRequiredError(reason)
    return key_owner_id


async def _resolve_obo_owner(
    config_pool: asyncpg.Pool,
    headers: list[tuple[bytes, bytes]],
    api_key: str,
    *,
    key_owner_id: str,
    surface: str,
    now: float | None,
) -> tuple[str | None, str]:
    """(owner_id de l'humain, "resolved") ou (None, raison de l'échec)."""
    any_header, all_headers = _obo_headers_present(headers)
    if not any_header:
        log.debug("obo.absent", surface=surface, owner=key_owner_id[:8])
        return None, "absent"
    if not all_headers:
        log.warning("obo.incomplete_headers", surface=surface, owner=key_owner_id[:8])
        return None, "incomplete_headers"

    actor = read_obo_actor(headers, api_key, now=now)
    if actor is None:
        log.warning("obo.invalid_signature", surface=surface, owner=key_owner_id[:8])
        return None, "invalid_signature"

    email = await email_for_identity(config_pool, actor)
    if email is None:
        log.warning("obo.unknown_identity", surface=surface, actor=actor[:8])
        return None, "unknown_identity"

    owner_id = principal_to_owner_id(email)
    log.debug("obo.resolved", surface=surface, actor=actor[:8], owner=owner_id[:8])
    return owner_id, "resolved"


# Clés du CORPS de `/api/v1/search` exigeant l'OBO. Mêmes conditions de
# validité que les lookups de clé (non révoquée, hors grâce expirée) : une clé
# invalide est laissée à l'authentification du service, qui la refuse en 401.
_REQUIRE_OBO_KEY_SQL = """
    SELECT owner_id
    FROM user_api_keys
    WHERE fingerprint = $1
      AND require_obo
      AND revoked_at IS NULL
      AND (rotated_at IS NULL OR rotated_at > now() - interval '72 hours')
"""


async def resolve_obo_for_body_keys(
    config_pool: asyncpg.Pool,
    headers: list[tuple[bytes, bytes]],
    api_keys: list[str],
    *,
    surface: str,
) -> None:
    """Lève `OboRequiredError` si une clé « OBO obligatoire » du corps n'a pas d'OBO.

    Sur cette surface la clé voyage dans le corps et non dans le Bearer : le
    secret de signature reste LA clé concernée. Plusieurs clés exigeant l'OBO
    dans un même appel ne peuvent donc pas toutes être satisfaites (un seul jeu
    d'en-têtes) — c'est voulu : chaque humain signe pour sa clé.
    """
    for api_key in dict.fromkeys(api_keys):
        fingerprint = sha256(api_key.encode("utf-8")).hexdigest()
        key_owner_id = await config_pool.fetchval(_REQUIRE_OBO_KEY_SQL, fingerprint)
        if key_owner_id is None:
            continue
        await resolve_effective_owner_id(
            config_pool,
            headers,
            api_key,
            key_owner_id=key_owner_id,
            surface=surface,
            require_obo=True,
        )
