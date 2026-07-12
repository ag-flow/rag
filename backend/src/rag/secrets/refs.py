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


def as_vault_ref(ref: str, default_vault_name: str) -> str:
    """Normalise un `api_key_ref` en ref vault complète, sans double-wrapper.

    Un `indexer_configs.api_key_ref` peut être stocké soit sous forme de clé
    logique (à préfixer avec le vault par défaut), soit déjà comme ref complète
    ``${vault://<name>:<path>}``. Wrapper inconditionnellement une ref déjà
    complète produirait ``${vault://X:${vault://...}}``, non parsable par le
    resolver. Helper transversal partagé par les sites qui résolvent une clé
    indexer (services/mcp, api/mcp_standard, api/playground) — corrige
    l'incohérence BUG-022 / BUG-024, où seul `RealIndexer` gérait les deux
    formats.
    """
    if is_vault_ref(ref):
        return ref
    return build_ref(default_vault_name, ref)
