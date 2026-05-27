from __future__ import annotations

import asyncpg

from rag.api.errors import ModelInUse, ModelNotSupported
from rag.db.helpers import fetch_all, fetch_one
from rag.schemas.admin import ModelEntry


async def list_models(config_pool: asyncpg.Pool) -> list[ModelEntry]:
    rows = await fetch_all(
        config_pool,
        "SELECT provider, model, dimension FROM model_dimensions ORDER BY provider, model",
    )
    return [
        ModelEntry(provider=r["provider"], model=r["model"], dimension=r["dimension"]) for r in rows
    ]


async def add_model(
    config_pool: asyncpg.Pool, *, provider: str, model: str, dimension: int
) -> None:
    """Ajoute une entrée. Lève `asyncpg.UniqueViolationError` si elle existe.

    Pour les models on laisse remonter UniqueViolationError ;
    l'`api/admin.py` mappe en 409.
    """
    async with config_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO model_dimensions (provider, model, dimension) VALUES ($1, $2, $3)",
            provider,
            model,
            dimension,
        )


async def delete_model(config_pool: asyncpg.Pool, *, provider: str, model: str) -> None:
    """Retire une entrée. Lève `ModelInUse` si un workspace l'utilise."""
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
            "DELETE FROM model_dimensions WHERE provider=$1 AND model=$2",
            provider,
            model,
        )


async def get_dimension_or_raise(config_pool: asyncpg.Pool, *, provider: str, model: str) -> int:
    """Lookup (provider, model) → dimension. Lève `ModelNotSupported` si miss."""
    row = await fetch_one(
        config_pool,
        "SELECT dimension FROM model_dimensions WHERE provider=$1 AND model=$2",
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
