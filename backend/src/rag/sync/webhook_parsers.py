from __future__ import annotations

from typing import Any

_HEADS_PREFIX = "refs/heads/"


def extract_branch(provider: str, payload: dict[str, Any]) -> str | None:
    """Extrait le nom de branche depuis un payload de push webhook.

    Retourne None si le payload n'est pas un push sur une branche
    (ex: tag, ping, event non-push) ou si le provider est inconnu.
    """
    match provider:
        case "github" | "gitea" | "gitlab":
            return _from_ref(payload.get("ref", ""))
        case "bitbucket":
            return _from_bitbucket(payload)
        case "azure-devops":
            return _from_azure(payload)
        case _:
            return None


def _from_ref(ref: str) -> str | None:
    if ref.startswith(_HEADS_PREFIX):
        return ref[len(_HEADS_PREFIX):]
    return None


def _from_bitbucket(payload: dict[str, Any]) -> str | None:
    try:
        changes: list[Any] = payload["push"]["changes"]
        if not changes:
            return None
        return str(changes[0]["new"]["name"])
    except (KeyError, IndexError, TypeError):
        return None


def _from_azure(payload: dict[str, Any]) -> str | None:
    try:
        updates: list[Any] = payload["resource"]["refUpdates"]
        if not updates:
            return None
        return _from_ref(str(updates[0]["name"]))
    except (KeyError, IndexError, TypeError):
        return None
