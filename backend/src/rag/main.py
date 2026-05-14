from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI

from rag.api.health import build_health_router
from rag.config import Settings
from rag.db.migrations import run_migrations
from rag.db.pool import WorkspacePoolRegistry
from rag.logging_setup import setup_logging
from rag.secrets.resolver import SecretResolver, VaultClient
from rag.secrets.vault import HarpocrateVaultClient

log = structlog.get_logger(__name__)

ResolverFactory = Callable[[Settings], SecretResolver]


def _default_resolver_factory(settings: Settings) -> SecretResolver:
    """Construit le SecretResolver à partir des api_keys Harpocrate de Settings."""
    clients: dict[str, VaultClient] = {
        identifier: HarpocrateVaultClient(url=str(cfg.url), token=cfg.token.get_secret_value())
        for identifier, cfg in settings.harpocrate_api_keys.items()
    }
    return SecretResolver(harpocrate_clients=clients)


def _default_migrations_dir() -> Path:
    """Dossier des migrations SQL — résolu relativement à ce fichier."""
    return Path(__file__).resolve().parents[2] / "migrations"


def build_app(
    *,
    version: str = "0.1.0",
    git_sha: str | None = None,
    resolver_factory: ResolverFactory = _default_resolver_factory,
    migrations_dir: Path | None = None,
) -> FastAPI:
    """Factory FastAPI — paramètres injectables pour les tests.

    Le lifespan :
    1. ouvre les pools `config` + `admin` via `WorkspacePoolRegistry.start()`,
    2. applique les migrations SQL sur `rag_config`,
    3. construit le `SecretResolver` et l'attache à `app.state.resolver`,
    4. expose la `master_key` sur `app.state.master_key` (consommée par
       `require_master_key`),
    5. ferme proprement tous les pools à l'arrêt.
    """
    settings = Settings()  # type: ignore[call-arg]
    setup_logging(settings.log_level, settings.environment)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log.info("app.lifespan.start", environment=settings.environment)

        app.state.master_key = settings.rag_master_key.get_secret_value()
        app.state.version = version
        app.state.git_sha = git_sha or os.environ.get("GIT_SHA", "unknown")
        app.state.environment = settings.environment

        registry = WorkspacePoolRegistry(
            config_dsn=str(settings.database_url),
            admin_dsn=str(settings.rag_postgres_admin_url),
        )
        await registry.start()
        app.state.pools = registry

        target_dir = migrations_dir or _default_migrations_dir()
        await run_migrations(registry.config_pool, target_dir)

        app.state.resolver = resolver_factory(settings)

        log.info("app.lifespan.ready")
        try:
            yield
        finally:
            log.info("app.lifespan.shutdown")
            await registry.close_all()

    app = FastAPI(
        title="ag-flow.rag",
        version=version,
        lifespan=lifespan,
    )
    app.include_router(build_health_router())
    return app


# Pas de `app` module-level — le Dockerfile invoque uvicorn avec `--factory`
# sur `rag.main:build_app`, ce qui appelle la factory au démarrage du serveur
# et laisse une éventuelle ValidationError (env var manquante) remonter
# proprement. L'alternative `try/except + app=None` masquait les vraies erreurs
# de configuration au runtime (NoneType is not callable peu lisible).
# En tests, on importe `build_app` directement et la fixture pose les env
# avant l'appel.
