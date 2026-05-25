from __future__ import annotations

import re

_VAULT_RE = re.compile(r"^\$\{vault://([^:}]+):([^}]+)\}$")


def parse_ref(ref: str) -> tuple[str, str]:
    match = _VAULT_RE.match(ref)
    if not match:
        raise ValueError(f"ref Harpocrate invalide: {ref!r}")
    return match.group(1), match.group(2)


def build_ref(vault_name: str, path: str) -> str:
    return f"${{vault://{vault_name}:{path}}}"


def is_vault_ref(value: str) -> bool:
    return bool(_VAULT_RE.match(value))
