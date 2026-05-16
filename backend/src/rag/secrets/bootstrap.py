from __future__ import annotations

import structlog
from asyncpg import Pool

from rag.config import Settings
from rag.schemas.harpocrate_vaults import VaultCreateRequest
from rag.services.harpocrate_vaults import HarpocrateVaultsService

log = structlog.get_logger(__name__)


async def seed_vaults_from_env_if_empty(
    *,
    settings: Settings,
    pool: Pool,
    vaults_service: HarpocrateVaultsService,
) -> int:
    """Seed automatique d'un coffre par paire HARPOCRATE_API_TOKEN_<ID> /
    HARPOCRATE_API_URL_<ID> si la table est vide ET les env vars présentes ET
    HARPOCRATE_DEK fourni.

    Préserve les refs ``${vault://rag:...}`` déjà semées en DB sans migration
    data, via ``name=<identifier.lower()>`` qui matche les refs hardcodées
    historiques.

    Returns:
        Nombre de coffres créés (0 si skip).
    """
    async with pool.acquire() as conn:
        existing = await vaults_service.list_all(conn)
        if existing:
            log.info(
                "vault.seed.skipped",
                reason="table non vide",
                count=len(existing),
            )
            return 0

        if not settings.harpocrate_api_keys:
            log.info("vault.seed.skipped", reason="env vide")
            return 0

        if settings.harpocrate_dek is None:
            log.error("vault.seed.aborted", reason="HARPOCRATE_DEK manquant")
            return 0

        identifiers = sorted(settings.harpocrate_api_keys.keys())
        default_id = identifiers[0]
        created = 0
        async with conn.transaction():
            for identifier in identifiers:
                cfg = settings.harpocrate_api_keys[identifier]
                req = VaultCreateRequest(
                    name=identifier.lower(),
                    label=f"Coffre {identifier} (seed env)",
                    base_url=str(cfg.url).rstrip("/"),
                    api_key_id=f"env:{identifier}",
                    api_key=cfg.token.get_secret_value(),
                    probe_path=None,
                    is_default=(identifier == default_id),
                )
                await vaults_service.create(conn, req)
                created += 1
                log.info(
                    "vault.seed.created",
                    name=req.name,
                    is_default=req.is_default,
                )
        return created
