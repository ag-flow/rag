from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI

from rag.api.admin import build_admin_router
from rag.api.errors import register_error_handlers
from rag.api.health import build_health_router
from rag.api.mcp import build_mcp_router
from rag.api.workspace import build_workspace_router
from rag.auth.workspace_auth import ApiKeyCache
from rag.config import Settings
from rag.db.migrations import run_migrations
from rag.db.pool import WorkspacePoolRegistry
from rag.logging_setup import setup_logging
from rag.secrets.resolver import SecretResolver, VaultClient
from rag.secrets.vault import HarpocrateVaultClient

log = structlog.get_logger(__name__)

ResolverFactory = Callable[[Settings], SecretResolver]


class _LazyHarpocrateVaultClient:
    """Wrapper paresseux : le SDK n'est instancié qu'au premier `get_secret`.

    Évite que le boot du service échoue si le token est invalide ou si le
    coffre est indisponible — l'erreur est levée seulement quand un secret
    est réellement résolu (ce que M1 ne fait pas).
    """

    def __init__(self, identifier: str, url: str, token: str) -> None:
        self._identifier = identifier
        self._url = url
        self._token = token
        self._real: HarpocrateVaultClient | None = None

    def get_secret(self, path: str) -> str:
        if self._real is None:
            log.info("vault.client.init", identifier=self._identifier)
            self._real = HarpocrateVaultClient(url=self._url, token=self._token)
        return self._real.get_secret(path)


def _default_resolver_factory(settings: Settings) -> SecretResolver:
    """Construit le SecretResolver à partir des api_keys Harpocrate de Settings.

    Les clients Harpocrate sont instanciés paresseusement (cf.
    `_LazyHarpocrateVaultClient`) — le boot du service ne dépend pas de la
    validité du token tant qu'aucun secret n'est résolu.
    """
    clients: dict[str, VaultClient] = {
        identifier: _LazyHarpocrateVaultClient(
            identifier=identifier,
            url=str(cfg.url),
            token=cfg.token.get_secret_value(),
        )
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
        app.state.admin_dsn = str(settings.rag_postgres_admin_url)

        target_dir = migrations_dir or _default_migrations_dir()
        await run_migrations(registry.config_pool, target_dir)

        app.state.resolver = resolver_factory(settings)

        # M3 : recovery au boot (jobs running orphelins → error)
        from rag.sync.recovery import reset_stale_running_jobs

        await reset_stale_running_jobs(registry.config_pool)

        # M4a : démarre le sync worker avec RealIndexer (remplace NoOpIndexer)
        # M4b : indexer aussi exposé sur app.state pour le router push synchrone
        from rag.indexer.real import RealIndexer
        from rag.sync.repo_storage import RepoStorage
        from rag.sync.worker import SyncWorker

        indexer = RealIndexer(
            config_pool=registry.config_pool,
            pool_registry=registry,
            secret_resolver=app.state.resolver,
        )
        app.state.indexer = indexer
        app.state.apikey_cache = ApiKeyCache(max_size=256, ttl_seconds=300)

        sync_worker = SyncWorker(
            config_pool=registry.config_pool,
            storage=RepoStorage(root=settings.sync_repos_root),
            indexer=indexer,
            resolver=app.state.resolver,
            poll_interval_seconds=settings.sync_worker_poll_interval_seconds,
            default_sync_interval_seconds=settings.sync_default_interval_seconds,
        )
        await sync_worker.start()
        app.state.sync_worker = sync_worker

        log.info("app.lifespan.ready")
        try:
            yield
        finally:
            log.info("app.lifespan.shutdown")
            if hasattr(app.state, "sync_worker"):
                await app.state.sync_worker.stop()
            await registry.close_all()

    app = FastAPI(
        title="ag-flow.rag",
        version=version,
        lifespan=lifespan,
    )
    app.include_router(build_health_router())
    app.include_router(build_admin_router())
    app.include_router(build_workspace_router())
    app.include_router(build_mcp_router())
    register_error_handlers(app)
    return app


# Pas de `app` module-level — le Dockerfile invoque uvicorn avec `--factory`
# sur `rag.main:build_app`, ce qui appelle la factory au démarrage du serveur
# et laisse une éventuelle ValidationError (env var manquante) remonter
# proprement. L'alternative `try/except + app=None` masquait les vraies erreurs
# de configuration au runtime (NoneType is not callable peu lisible).
# En tests, on importe `build_app` directement et la fixture pose les env
# avant l'appel.
