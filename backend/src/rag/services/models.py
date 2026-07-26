from __future__ import annotations

import asyncpg

from rag.api.errors import ModelInUse, ModelNotOwned, ModelNotSupported
from rag.db.helpers import fetch_all, fetch_one
from rag.schemas.admin import ModelEntry


async def list_models(config_pool: asyncpg.Pool, *, owner_id: str) -> list[ModelEntry]:
    """Catalogue système (owner_id NULL) + modèles du caller, jamais ceux des autres."""
    rows = await fetch_all(
        config_pool,
        "SELECT provider, model, kind, dimension, created_at, owner_id"
        " FROM model_dimensions"
        " WHERE owner_id IS NULL OR owner_id = $1"
        " ORDER BY provider, model",
        owner_id,
    )
    return [
        ModelEntry(
            provider=r["provider"],
            model=r["model"],
            kind=r["kind"],
            dimension=r["dimension"],
            created_at=r["created_at"].isoformat() if r["created_at"] else None,
            is_system=r["owner_id"] is None,
        )
        for r in rows
    ]


# Capacité IA (protocole d'appel) par plateforme d'accès — cf. factory.
# Les plateformes absentes de la table sont OpenAI-compatibles par défaut.
_SERVICE_BY_PROVIDER: dict[str, str] = {
    "openai": "openai",
    "voyage": "voyage",
    "mistral": "mistral",
    "jina": "jina",
    "gemini": "gemini",
    "dashscope": "dashscope",
    "ollama": "ollama",
    "ollama-cloud": "ollama",
    "bedrock": "bedrock",
}


def service_for_provider(provider: str) -> str:
    """Service (protocole) à router pour une plateforme donnée."""
    return _SERVICE_BY_PROVIDER.get(provider, "openai")


async def add_model(
    config_pool: asyncpg.Pool,
    *,
    provider: str,
    model: str,
    dimension: int | None,
    owner_id: str,
    kind: str = "embedding",
) -> None:
    """Ajoute une entrée dans la bibliothèque du caller.

    L'unicité (provider, model) est GLOBALE (les jointures de résolution
    reposent dessus) : on laisse remonter UniqueViolationError, mappée en 409
    par l'API — le doublon peut appartenir au catalogue ou à un autre user.
    """
    async with config_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO model_dimensions (provider, model, dimension, owner_id, kind, service)"
            " VALUES ($1, $2, $3, $4, $5, $6)",
            provider,
            model,
            dimension,
            owner_id,
            kind,
            service_for_provider(provider),
        )


async def delete_model(
    config_pool: asyncpg.Pool, *, provider: str, model: str, owner_id: str
) -> None:
    """Retire une entrée de la bibliothèque du caller.

    Lève `ModelInUse` si un workspace l'utilise, `ModelNotOwned` si l'entrée
    est du catalogue système (immuable) ou appartient à un autre utilisateur.
    Silencieux si l'entrée n'existe pas (idempotent, comportement historique).
    """
    row = await fetch_one(
        config_pool,
        "SELECT owner_id FROM model_dimensions WHERE provider=$1 AND model=$2",
        provider,
        model,
    )
    if row is None:
        return
    if row["owner_id"] is None or row["owner_id"] != owner_id:
        raise ModelNotOwned(provider, model, is_system=row["owner_id"] is None)

    workspaces_using = await fetch_all(
        config_pool,
        """
        SELECT w.name
        FROM indexer_configs ic
        JOIN workspaces w ON w.id = ic.workspace_id
        WHERE ic.provider = $1 AND ic.model = $2
        """,
        provider,
        model,
    )
    if workspaces_using:
        raise ModelInUse(provider, model, [r["name"] for r in workspaces_using])

    async with config_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM model_dimensions WHERE provider=$1 AND model=$2 AND owner_id=$3",
            provider,
            model,
            owner_id,
        )


async def get_dimension_or_raise(config_pool: asyncpg.Pool, *, provider: str, model: str) -> int:
    """Lookup (provider, model) → dimension. Lève `ModelNotSupported` si miss."""
    row = await fetch_one(
        config_pool,
        "SELECT dimension FROM model_dimensions "
        "WHERE provider=$1 AND model=$2 AND kind='embedding'",
        provider,
        model,
    )
    if row is None:
        all_models = await fetch_all(
            config_pool, "SELECT provider, model FROM model_dimensions ORDER BY provider, model"
        )
        supported = [(r["provider"], r["model"]) for r in all_models]
        raise ModelNotSupported(provider=provider, model=model, supported=supported)
    return int(row["dimension"])
