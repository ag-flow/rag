from __future__ import annotations

import re

import structlog

from rag.api.errors import InvalidPath, UnresolvedTemplateVariable

log = structlog.get_logger(__name__)

_PATH_MAX_LEN = 1024
_BAD_SEGMENT = re.compile(r"(^|/)\.\.(/|$)")
# Placeholder de gabarit resté littéral : `{event.blockSlug}`, `{title}`. Seuls
# des identifiants (pointés ou non) entre accolades : une accolade isolée ou un
# objet JSON ne correspond pas.
_UNRESOLVED_PLACEHOLDER = re.compile(r"\{[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\}")


def normalize_path(raw: str) -> str:
    """Normalise et valide un path POSIX relatif.

    - remplace ``\\`` par ``/``
    - rejette : NUL byte, leading ``/``, segments ``..``, vide, > 1024 chars
    """
    if "\x00" in raw:
        raise InvalidPath("path_contains_nul")
    p = raw.replace("\\", "/")
    if p.startswith("/"):
        raise InvalidPath("path_must_be_relative")
    if _BAD_SEGMENT.search(p):
        raise InvalidPath("path_traversal_forbidden")
    if not p or len(p) > _PATH_MAX_LEN:
        raise InvalidPath("path_invalid_length")
    return p


def reject_unresolved_placeholders(*, workspace: str, path: str, title: str | None) -> None:
    """Refuse un push dont le path ou le titre porte une variable de gabarit
    non substituée par l'émetteur.

    L'automate docflow a longtemps envoyé `{event.blockSlug}` tel quel : chemins
    inutilisables et en-tête de chunk embeddé avec la chaîne parasite, sans que
    rien ne le signale (ticket 14a62570). Refuser plutôt qu'indexer en silence :
    l'émetteur reçoit un 422 qui nomme les variables. Le CONTENU n'est pas
    contrôlé, volontairement : une doc peut légitimement citer `{title}`. Le
    DELETE n'appelle pas cette garde, pour pouvoir purger les paths pollués.
    """
    for field, value in (("path", path), ("title", title)):
        if value is None:
            continue
        variables = _UNRESOLVED_PLACEHOLDER.findall(value)
        if variables:
            log.warning(
                "push.rejected_unresolved_template_variable",
                workspace=workspace,
                field=field,
                variables=variables,
            )
            raise UnresolvedTemplateVariable(field, variables)
