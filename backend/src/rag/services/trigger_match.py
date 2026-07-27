from __future__ import annotations

from typing import Protocol
from uuid import UUID

import asyncpg

from rag.globmatch import most_specific_index


class _Fetcher(Protocol):
    """Pool ou connexion asyncpg — seul `fetch` est requis."""

    async def fetch(self, query: str, *args: object) -> list[asyncpg.Record]: ...


_QUERY_ALL = (
    "SELECT id, pattern, strategy_id FROM workspace_extension_triggers "
    "WHERE workspace_id = $1::uuid AND enabled ORDER BY created_at"
)
_QUERY_WITH_STRATEGY = (
    "SELECT id, pattern, strategy_id FROM workspace_extension_triggers "
    "WHERE workspace_id = $1::uuid AND enabled AND strategy_id IS NOT NULL "
    "ORDER BY created_at"
)


async def resolve_trigger(
    executor: _Fetcher,
    *,
    workspace_id: UUID | str,
    path: str,
    require_strategy: bool = False,
) -> asyncpg.Record | None:
    """Trigger de workspace applicable à `path` — le plus spécifique gagne.

    Depuis la migration 089 un trigger cible un PATTERN GLOB sur le chemin
    complet (`backlog/**/*.md`), plus une extension. Plusieurs triggers
    peuvent matcher un même fichier ; un seul s'applique, pour la stratégie
    de chunking comme pour les prompts d'enrichissement. Départage :
    (1) le plus de segments dans le pattern, (2) le pattern le plus long,
    (3) le plus ancien créé (ordre SQL stable).

    `require_strategy=True` restreint aux triggers portant un binding de
    stratégie (résolution de chunking) ; sans lui, tout trigger actif est
    candidat (prompts d'enrichissement).
    """
    rows = await executor.fetch(
        _QUERY_WITH_STRATEGY if require_strategy else _QUERY_ALL,
        workspace_id,
    )
    index = most_specific_index([r["pattern"] for r in rows], path)
    return rows[index] if index is not None else None
