from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from rag.main import build_app
from rag.secrets.resolver import VaultLookupFailed

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _ApiStubResolver:
    """Resolveur stub : accepte tout `${vault://rag:<known>}` ou `${vault://test:<known>}`,
    refuse le reste.

    Supporte deux catégories de refs :
    - refs logiques connues (openai_embedding_key, voyage_api_key, etc.) → value-of-<logical>
    - refs workspace (wsapi_<name>) → résolu depuis `_secret_store` si présent

    `_secret_store` est partagé avec le stub HarpocrateVaultsService pour que
    `write_secret` persiste la valeur et que le resolver puisse la restituer
    (comportement cohérent pour les tests GET /apikey et MCP auth).
    """

    def __init__(self, secret_store: dict[str, str]) -> None:
        self._secret_store = secret_store
        self.known: set[str] = {
            "openai_embedding_key",
            "voyage_api_key",
            "github_token",
            "vk",
            "k",
        }

    async def resolve(self, ref: str) -> str:
        return await self.resolve_with_retry(ref)

    async def resolve_with_retry(self, ref: str) -> str:
        import re

        m = re.fullmatch(r"\$\{vault://[^:]+:([^}]+)\}", ref)
        if m is None:
            raise AssertionError(f"unexpected ref {ref}")
        logical = m.group(1)
        if logical in self.known:
            return f"value-of-{logical}"
        # Refs workspace (wsapi_<name>) : lookup dans le store partagé.
        if logical in self._secret_store:
            return self._secret_store[logical]
        raise VaultLookupFailed(f"no secret {logical}")


class _ApiStubClientProvider:
    """Stub `HarpocrateClientProvider` : default vault toujours 'rag'.

    Surchargé via le `resolver_factory` du conftest pour que les routers M5c
    (qui appellent `app.state.client_provider.get_default_vault_name()`)
    reçoivent un nom de coffre sans s'appuyer sur la DB.
    """

    async def get_default_vault_name(self) -> str | None:
        return "rag"

    def invalidate(self) -> None:
        pass


def _make_stub_harpocrate_vaults_service(
    secret_store: dict[str, str],
) -> MagicMock:
    """Stub HarpocrateVaultsService pour les tests API.

    get_by_name retourne un VaultSummary mock (vault "rag" existe toujours).
    write_secret persiste la valeur dans `secret_store` (partagé avec le resolver).
    delete_secret efface la valeur du store.
    bind_client_provider est un no-op.
    """
    from rag.schemas.harpocrate_vaults import VaultSummary

    service = MagicMock()
    vault = MagicMock(spec=VaultSummary)
    vault.id = uuid4()
    vault.base_url = "http://harpocrate-stub:8200"
    vault.name = "rag"
    service.get_by_name = AsyncMock(return_value=vault)

    async def _write_secret(_conn, *, vault_name: str, path: str, value: str) -> None:
        secret_store[path] = value

    async def _delete_secret(_conn, *, vault_name: str, path: str) -> None:
        secret_store.pop(path, None)

    service.write_secret = _write_secret
    service.delete_secret = _delete_secret
    service.bind_client_provider = MagicMock(return_value=None)
    return service


@pytest_asyncio.fixture
async def admin_client(
    pg_container: str,
) -> AsyncIterator[TestClient]:
    os.environ["DATABASE_URL"] = pg_container
    os.environ["RAG_POSTGRES_ADMIN_URL"] = pg_container.rsplit("/", 1)[0] + "/postgres"
    # Force-set (pas setdefault) : évite la pollution d'env entre modules de test.
    os.environ["RAG_MASTER_KEY"] = "mk_test_e2e_padding_padding_padding_padding"
    os.environ.setdefault("RAG_PUBLIC_URL", "http://localhost:8000")
    # Pas de HARPOCRATE_API_TOKEN_RAG/URL_RAG : on évite que `seed_vaults_from_env_if_empty`
    # auto-crée un coffre "rag" au boot, ce qui polluerait les tests qui veulent piloter
    # la table eux-mêmes (notamment test_admin_harpocrate_vaults.py).
    # Les tests qui consomment des refs `${vault://rag:...}` passent par `_ApiStubResolver`
    # injecté via `resolver_factory`, indépendant de settings.harpocrate_api_keys.
    os.environ.pop("HARPOCRATE_API_TOKEN_RAG", None)
    os.environ.pop("HARPOCRATE_API_URL_RAG", None)
    os.environ.setdefault(
        "HARPOCRATE_DEK",
        "passphrase-of-at-least-32-characters-long",
    )
    # RAG_API_KEY_DEK retiré — les api_keys workspace sont désormais stockées
    # dans Harpocrate (migration 015). On s'assure qu'il n'est PAS dans l'env
    # pour les tests (déjà absent par défaut, mais explicite ici).
    os.environ.pop("RAG_API_KEY_DEK", None)
    os.environ.setdefault("ENVIRONMENT", "dev")

    # Store partagé entre le stub Harpocrate et le resolver :
    # write_secret persiste ici, resolve_with_retry lit ici.
    secret_store: dict[str, str] = {}
    stub_harpo = _make_stub_harpocrate_vaults_service(secret_store)
    admin_resolver = _ApiStubResolver(secret_store)

    def _factory(_cfg, app_in):  # type: ignore[no-untyped-def]
        # Le lifespan a déjà branché un `client_provider` "réel" sur
        # `app.state` ; on le remplace par un stub qui retourne toujours
        # le coffre "rag" pour que les routers M5c puissent fonctionner
        # sans table `harpocrate_vaults` peuplée.
        app_in.state.client_provider = _ApiStubClientProvider()
        # Remplace le HarpocrateVaultsService par le stub pour que
        # create_workspace / rotate_apikey / delete ne s'appuient pas sur
        # la table harpocrate_vaults ni sur une instance Harpocrate réelle.
        app_in.state.harpocrate_vaults_service = stub_harpo
        return admin_resolver

    app = build_app(
        version="0.2.0",
        git_sha="testsha",
        resolver_factory=_factory,  # type: ignore[arg-type]
        migrations_dir=_MIGRATIONS_DIR,
    )
    with TestClient(app) as client:
        yield client


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer mk_test_e2e_padding_padding_padding_padding"}


@pytest.fixture
def cleanup_ws_dbs_api(pg_container: str) -> Iterator[None]:
    yield
    import asyncio

    async def _cleanup() -> None:
        admin = await asyncpg.connect(pg_container.rsplit("/", 1)[0] + "/postgres")
        try:
            for r in await admin.fetch(
                "SELECT datname FROM pg_database WHERE datname LIKE 'rag_ws_%'"
            ):
                await admin.execute(f'DROP DATABASE IF EXISTS "{r["datname"]}" WITH (FORCE)')
        finally:
            await admin.close()

    asyncio.get_event_loop().run_until_complete(_cleanup())
