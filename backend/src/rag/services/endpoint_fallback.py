"""Validation du fallback d'endpoint (enabler docflow f94bfd84).

Un endpoint peut déclarer UN endpoint de fallback, dans le même coffre.
Gardes à l'écriture : un seul niveau (ni chaîne ni cycle) et compatibilité
de vectorisation — les vecteurs de l'index étant liés au modèle d'embedding,
le fallback n'est accepté que si son service de vectorisation porte le même
modèle (et la même dimension déclarée) que le primaire. Rerank et LLM sont
libres (résultat substituable).
"""

from __future__ import annotations

from uuid import UUID

import asyncpg


class EndpointFallbackInvalidError(ValueError):
    """Configuration de fallback refusée (message pédagogique)."""


_DIMENSION = "SELECT dimension FROM model_dimensions WHERE provider = $1 AND model = $2"


async def validate_fallback(
    conn: asyncpg.Connection,
    *,
    endpoint_id: UUID,
    vault_id: UUID,
    fallback_id: UUID,
    indexer_provider: str,
    indexer_model: str,
) -> None:
    """Lève :class:`EndpointFallbackInvalidError` si la configuration est
    refusée. `indexer_provider`/`indexer_model` sont ceux du primaire TELS
    QU'ILS SERONT ÉCRITS (un PATCH qui change l'indexeur revalide)."""
    if fallback_id == endpoint_id:
        raise EndpointFallbackInvalidError("un endpoint ne peut pas être son propre fallback")
    fb = await conn.fetchrow(
        "SELECT vault_id, fallback_endpoint_id, indexer_provider, indexer_model "
        "FROM vault_endpoints WHERE id = $1",
        fallback_id,
    )
    if fb is None:
        raise EndpointFallbackInvalidError("endpoint de fallback introuvable")
    if fb["vault_id"] != vault_id:
        raise EndpointFallbackInvalidError(
            "le fallback doit appartenir au même coffre que le primaire"
        )
    if fb["fallback_endpoint_id"] is not None:
        raise EndpointFallbackInvalidError(
            "un seul niveau de fallback : l'endpoint choisi déclare lui-même un fallback"
        )
    referenced = await conn.fetchval(
        "SELECT COUNT(*) FROM vault_endpoints WHERE fallback_endpoint_id = $1", endpoint_id
    )
    if int(referenced or 0) > 0:
        raise EndpointFallbackInvalidError(
            "un seul niveau de fallback : cet endpoint est déjà le fallback "
            "d'un autre endpoint, il ne peut pas déclarer le sien"
        )
    if fb["indexer_model"] != indexer_model:
        raise EndpointFallbackInvalidError(
            "vectorisation incompatible : le fallback doit servir le même modèle "
            f"d'embedding que le primaire ({indexer_model}), il déclare "
            f"{fb['indexer_model']} — les vecteurs de l'index sont liés au modèle "
            "(rerank et LLM restent substituables librement)"
        )
    dim_primary = await conn.fetchval(_DIMENSION, indexer_provider, indexer_model)
    dim_fallback = await conn.fetchval(_DIMENSION, fb["indexer_provider"], fb["indexer_model"])
    if dim_primary is not None and dim_fallback is not None and dim_primary != dim_fallback:
        raise EndpointFallbackInvalidError(
            "vectorisation incompatible : dimensions déclarées différentes "
            f"({dim_primary} vs {dim_fallback})"
        )
