from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg
from pydantic import BaseModel, ValidationError

from rag.services import chunking_strategies as strategies_svc
from rag.services import prompt_templates as templates_svc

WRITE_REFUSAL = "Écriture refusée : la clé API n'a pas le grant can_write sur ce workspace."

# Erreurs attendues des services et de la validation : traduites en message
# pédagogique par `explain` — jamais propagées à l'agent en exception brute.
EXPECTED_ERRORS: tuple[type[Exception], ...] = (
    strategies_svc.StrategyNotFoundError,
    strategies_svc.StrategyImmutableError,
    strategies_svc.StrategySlugConflictError,
    strategies_svc.StrategyInUseError,
    strategies_svc.InvalidStrategyError,
    templates_svc.TemplateNotFoundError,
    templates_svc.TemplateImmutableError,
    templates_svc.TemplateInUseError,
    asyncpg.UniqueViolationError,
    ValidationError,
    ValueError,  # UUID invalide, mode inconnu — ValidationError en hérite déjà
)


def parse_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"identifiant invalide : {value!r} n'est pas un UUID") from exc


def write_refusal(ctx: Any) -> str | None:
    """Message de refus si la clé n'a pas can_write, None sinon."""
    return None if ctx.can_write else WRITE_REFUSAL


def dump(payload: Any) -> str:
    """JSON indenté ensure_ascii=False (pattern index_status), modèles inclus."""
    return json.dumps(_plain(payload), ensure_ascii=False, indent=2, default=str)


def _plain(payload: Any) -> Any:
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    if isinstance(payload, list):
        return [_plain(p) for p in payload]
    if isinstance(payload, dict):
        return {k: _plain(v) for k, v in payload.items()}
    return payload


def explain(exc: Exception) -> str:
    """Traduit une erreur métier en message explicite et actionnable."""
    if isinstance(exc, strategies_svc.StrategyNotFoundError):
        return (
            f"Stratégie introuvable : {exc}. Elle n'existe pas ou n'est pas visible depuis "
            "ta bibliothèque — vérifie l'id via list_chunking_strategies()."
        )
    if isinstance(exc, strategies_svc.StrategyImmutableError):
        return (
            "Stratégie système immuable : ni modifiable ni supprimable. "
            "Duplique-la avec duplicate_chunking_strategy pour obtenir une copie personnalisable."
        )
    if isinstance(exc, strategies_svc.StrategySlugConflictError):
        return (
            f"Slug déjà utilisé : '{exc}' existe déjà dans la bibliothèque "
            "(le slug est dérivé du label). Choisis un label différent."
        )
    if isinstance(exc, strategies_svc.StrategyInUseError):
        return f"Suppression refusée : {exc}. Détache d'abord ces références."
    if isinstance(exc, strategies_svc.InvalidStrategyError):
        return f"Spécification invalide : {exc}"
    if isinstance(exc, templates_svc.TemplateNotFoundError):
        return (
            f"Template introuvable : {exc}. Il n'existe pas ou n'est pas visible depuis "
            "ta bibliothèque — vérifie l'id via list_prompt_templates()."
        )
    if isinstance(exc, templates_svc.TemplateImmutableError):
        return (
            "Template système immuable : ni modifiable ni supprimable. "
            "Crée ton propre template avec create_prompt_template."
        )
    if isinstance(exc, templates_svc.TemplateInUseError):
        return f"Suppression refusée : {exc}. Retire d'abord ces bindings."
    if isinstance(exc, asyncpg.UniqueViolationError):
        return "Nom déjà utilisé dans ta bibliothèque : choisis un nom différent."
    return f"Paramètres invalides : {exc}"
