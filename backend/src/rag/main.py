from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from rag.api.admin import build_admin_router
from rag.api.admin_harpocrate_vaults import router as admin_harpocrate_vaults_router
from rag.api.admin_oidc import build_admin_oidc_router
from rag.api.admin_provider_keys import router as admin_provider_keys_router
from rag.api.admin_webhooks import build_webhooks_router
from rag.api.auth import build_auth_router
from rag.api.auth_methods import build_auth_methods_router
from rag.api.errors import register_error_handlers
from rag.api.health import build_health_router
from rag.api.mcp import build_mcp_router
from rag.api.workspace import build_workspace_router
from rag.api.ws import router as ws_router
from rag.auth.workspace_auth import ApiKeyCache
from rag.config import Settings
from rag.db.migrations import run_migrations
from rag.db.pool import WorkspacePoolRegistry
from rag.db.workspace_migrations import apply_pending_for_all_workspaces
from rag.logging_setup import setup_logging
from rag.secrets.client_provider import HarpocrateClientProvider
from rag.secrets.resolver import SecretResolver
from rag.services.harpocrate_vaults import HarpocrateVaultsService
from rag.services.local_auth import LocalAuthService
from rag.services.oidc import OidcService

log = structlog.get_logger(__name__)

ResolverFactory = Callable[[Settings, FastAPI], SecretResolver]


def _default_resolver_factory(settings: Settings, app: FastAPI) -> SecretResolver:
    """Factory par défaut : retourne un `SecretResolver` qui consomme le
    `HarpocrateClientProvider` posé sur `app.state.client_provider` par le
    lifespan (cf. `_build_client_provider`).

    Les factories stub (tests) peuvent retourner un resolver arbitraire
    bâti sur `harpocrate_clients={}` ; le `client_provider` reste branché
    en `app.state` et continue à servir les sites qui en ont besoin
    (routers, worker, OidcService).
    """
    return SecretResolver(client_provider=app.state.client_provider)


def _build_client_provider(settings: Settings, app: FastAPI) -> HarpocrateClientProvider:
    """Construit le `HarpocrateClientProvider` (DB-first + fallback env) et
    binde le `HarpocrateVaultsService` pour propager les invalidations cache.

    Prérequis : `app.state.pools` et `app.state.harpocrate_vaults_service`
    doivent déjà être initialisés.
    """
    vaults_service: HarpocrateVaultsService = app.state.harpocrate_vaults_service
    client_provider = HarpocrateClientProvider(
        settings=settings,
        vaults_service=vaults_service,
        db_pool=app.state.pools.config_pool,
    )
    vaults_service.bind_client_provider(client_provider)
    return client_provider


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
        app.state.settings = settings
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

        # Boot guard : si des workspaces existent en BDD, au moins un coffre
        # Harpocrate doit être configuré (sinon impossible de résoudre les
        # api_key_ref — service incohérent dès la première requête MCP).
        async with registry.config_pool.acquire() as conn:
            workspaces_count = await conn.fetchval("SELECT COUNT(*) FROM workspaces")
            vault_count = await conn.fetchval("SELECT COUNT(*) FROM harpocrate_vaults")
        if workspaces_count > 0 and vault_count == 0:
            raise RuntimeError(
                f"Incohérence : {workspaces_count} workspace(s) présent(s) mais "
                "aucun coffre Harpocrate configuré. Recréer un coffre via "
                "/ui/settings/harpocrate-vaults ou supprimer les workspaces."
            )

        # M9-T9 : boot scan — applique les migrations workspace manquantes sur
        # toutes les bases référencées dans la table `workspaces`. Fail-fast :
        # si une base est inaccessible ou si une migration plante, le lifespan
        # remonte l'exception et le service refuse de démarrer. Les logs
        # indiquent quel workspace a échoué (cf. apply_pending_for_all_workspaces).
        await apply_pending_for_all_workspaces(registry.config_pool)

        # Le service Harpocrate est créé ici (et non dans la factory) pour que
        # les tests qui injectent un `resolver_factory` stub bénéficient quand
        # même du service + du seed env (rétrocompat).
        app.state.harpocrate_vaults_service = HarpocrateVaultsService(settings)

        # Le `HarpocrateClientProvider` est branché en `app.state` AVANT le
        # resolver_factory pour que tous les sites (routers, worker, OidcService)
        # puissent appeler `await app.state.client_provider.get_default_vault_name()`,
        # même quand un test injecte un `resolver_factory` stub.
        app.state.client_provider = _build_client_provider(settings, app)

        # La factory par défaut retourne un `SecretResolver` qui consomme
        # `app.state.client_provider`. Les factories stub (tests) peuvent
        # retourner un resolver arbitraire ; `client_provider` reste attaché
        # à `app.state` indépendamment.
        app.state.resolver = resolver_factory(settings, app)

        app.state.oidc = OidcService(
            config_pool=registry.config_pool,
            secret_resolver=app.state.resolver,
            client_provider=app.state.client_provider,
            public_url=str(settings.rag_public_url).rstrip("/"),
        )
        app.state.public_url = str(settings.rag_public_url).rstrip("/")

        app.state.local_auth = LocalAuthService(
            username=settings.rag_bootstrap_admin_username,
            password_hash=settings.rag_bootstrap_admin_password_hash,
            ttl_seconds=settings.rag_bootstrap_session_ttl_seconds,
        )

        # M3 : recovery au boot (jobs running orphelins → error)
        from rag.sync.recovery import reset_stale_running_jobs

        await reset_stale_running_jobs(registry.config_pool)

        # M4a : démarre le sync worker avec RealIndexer (remplace NoOpIndexer)
        # M4b : indexer aussi exposé sur app.state pour le router push synchrone
        from rag.indexer.real import RealIndexer
        from rag.services.job_log_bus import JobLogBus
        from rag.sync.repo_storage import RepoStorage
        from rag.sync.worker import SyncWorker

        indexer = RealIndexer(
            config_pool=registry.config_pool,
            pool_registry=registry,
            secret_resolver=app.state.resolver,
            client_provider=app.state.client_provider,
        )
        app.state.indexer = indexer
        app.state.apikey_cache = ApiKeyCache()
        app.state.job_log_bus = JobLogBus()

        webhook_secret: str | None = (
            settings.rag_webhook_secret.get_secret_value()
            if settings.rag_webhook_secret
            else None
        )
        sync_worker = SyncWorker(
            config_pool=registry.config_pool,
            storage=RepoStorage(root=settings.sync_repos_root),
            indexer=indexer,
            resolver=app.state.resolver,
            client_provider=app.state.client_provider,
            poll_interval_seconds=settings.sync_worker_poll_interval_seconds,
            default_sync_interval_seconds=settings.sync_default_interval_seconds,
            job_log_bus=app.state.job_log_bus,
            webhook_secret=webhook_secret,
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
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.rag_session_secret.get_secret_value(),
        same_site="lax",
        https_only=(settings.environment != "dev"),
    )
    app.include_router(build_health_router())
    app.include_router(build_admin_router(), prefix="/api/admin")
    app.include_router(build_admin_oidc_router(), prefix="/api/admin")
    app.include_router(admin_harpocrate_vaults_router)
    app.include_router(admin_provider_keys_router)
    app.include_router(build_webhooks_router(), prefix="/api/admin")
    app.include_router(build_auth_router())
    app.include_router(build_auth_methods_router())
    app.include_router(build_workspace_router())
    app.include_router(build_mcp_router())
    app.include_router(ws_router)
    register_error_handlers(app)
    return app


# Pas de `app` module-level — le Dockerfile invoque uvicorn avec `--factory`
# sur `rag.main:build_app`, ce qui appelle la factory au démarrage du serveur
# et laisse une éventuelle ValidationError (env var manquante) remonter
# proprement. L'alternative `try/except + app=None` masquait les vraies erreurs
# de configuration au runtime (NoneType is not callable peu lisible).
# En tests, on importe `build_app` directement et la fixture pose les env
# avant l'appel.
