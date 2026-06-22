from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

_DEFAULT_CATEGORY = "prose"


@dataclass(frozen=True)
class RoutingConfig:
    """Cartes de routage déjà fusionnées (global + workspace).

    - `extension_categories` : extension (``.md``) → catégorie (``prose``).
    - `category_strategies`  : catégorie → nom de stratégie du catalogue.
    """

    extension_categories: dict[str, str]
    category_strategies: dict[str, str]


def merge_maps(global_map: dict[str, str], workspace_map: dict[str, str]) -> dict[str, str]:
    """Fusionne global puis workspace : le workspace surcharge clé par clé."""
    return {**global_map, **workspace_map}


def resolve_strategy_name(
    *,
    path: str | None,
    override: str | None,
    routing: RoutingConfig,
    default_category: str = _DEFAULT_CATEGORY,
) -> str:
    """Résout le nom de stratégie pour `path` (ADR 0001 §2).

    Priorité : override explicite → extension → catégorie → stratégie ; sinon
    catégorie par défaut. Lève `ValueError` si la catégorie par défaut elle-même
    n'a pas de stratégie (config invalide).
    """
    if override:
        return override

    category = routing.extension_categories.get(_extension(path), default_category)
    strategy = routing.category_strategies.get(category)
    if strategy is not None:
        return strategy

    default_strategy = routing.category_strategies.get(default_category)
    if default_strategy is None:
        raise ValueError(
            f"no strategy mapped for category {category!r} nor for default category "
            f"{default_category!r}"
        )
    return default_strategy


def _extension(path: str | None) -> str:
    if not path:
        return ""
    return PurePosixPath(path).suffix.lower()
