from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Protocol

import structlog

log = structlog.get_logger(__name__)


class UnknownAction(ValueError):  # noqa: N818 — nom imposé par la spec (formalisme déclaratif)
    """L'action déclarative n'est pas reconnue (`env://`, `vault://`)."""


class EnvVarMissing(KeyError):  # noqa: N818 — nom imposé par la spec (formalisme déclaratif)
    """La variable d'env référencée n'est pas dans `os.environ`."""


class VaultLookupFailed(RuntimeError):  # noqa: N818 — nom imposé par la spec (formalisme déclaratif)
    """Le coffre Harpocrate a refusé ou n'a pas trouvé le secret."""


@dataclass(frozen=True)
class ParsedRef:
    action: str
    api_key_id: str | None
    path: str


_ENV_RE = re.compile(r"^\$\{env://([^}]+)\}$")
_VAULT_RE = re.compile(r"^\$\{vault://([^:}]+):([^}]+)\}$")
_GENERIC_RE = re.compile(r"^\$\{([a-zA-Z][a-zA-Z0-9_-]*)://.*\}$")


def parse_ref(value: str) -> ParsedRef | None:
    """Parse une référence déclarative `${action://...}`.

    Retourne `None` si `value` n'est pas une référence (valeur littérale).
    Lève `UnknownAction` si la chaîne ressemble à une référence mais l'action
    n'est pas supportée.
    """
    if "${" not in value:
        return None

    if m := _ENV_RE.match(value):
        return ParsedRef(action="env", api_key_id=None, path=m.group(1))

    if m := _VAULT_RE.match(value):
        return ParsedRef(action="vault", api_key_id=m.group(1), path=m.group(2))

    if m := _GENERIC_RE.match(value):
        raise UnknownAction(f"Unknown declarative action: {m.group(1)!r}")

    return None


class VaultClient(Protocol):
    """Interface attendue d'un client Harpocrate (pour mocker en tests)."""

    def get_secret(self, path: str) -> str: ...


class SecretResolver:
    """Résolveur de références déclaratives `${env://}` / `${vault://}`.

    - Valeurs littérales : retournées telles quelles.
    - `${env://VAR}` : `os.environ[VAR]` (fail fast si absent).
    - `${vault://id:path}` : appel au `VaultClient` correspondant.
    """

    def __init__(self, harpocrate_clients: dict[str, VaultClient]) -> None:
        self._clients = harpocrate_clients

    def resolve(self, value: str) -> str:
        ref = parse_ref(value)
        if ref is None:
            return value

        if ref.action == "env":
            try:
                return os.environ[ref.path]
            except KeyError as e:
                raise EnvVarMissing(f"Environment variable not set: {ref.path}") from e

        if ref.action == "vault":
            return self._vault_lookup(ref.api_key_id, ref.path)

        raise UnknownAction(f"Unhandled action: {ref.action}")

    def _vault_lookup(self, api_key_id: str | None, path: str) -> str:
        if api_key_id is None:
            raise UnknownAction("vault:// requires an api_key_id")
        if api_key_id not in self._clients:
            raise VaultLookupFailed(
                f"No Harpocrate client configured for api_key_id={api_key_id!r}"
            )
        return self._clients[api_key_id].get_secret(path)
