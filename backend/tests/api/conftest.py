from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from rag.main import build_app
from rag.secrets.resolver import VaultLookupFailed

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _ApiStubResolver:
    """Resolveur stub : accepte tout `${vault://rag:<known>}`, refuse le reste."""

    def __init__(self) -> None:
        self.known: set[str] = {"openai_embedding_key", "voyage_api_key", "github_token", "vk", "k"}

    async def resolve(self, ref: str) -> str:
        return await self.resolve_with_retry(ref)

    async def resolve_with_retry(self, ref: str) -> str:
        import re

        m = re.fullmatch(r"\$\{vault://[^:]+:([^}]+)\}", ref)
        if m is None:
            raise AssertionError(f"unexpected ref {ref}")
        logical = m.group(1)
        if logical not in self.known:
            raise VaultLookupFailed(f"no secret {logical}")
        return f"value-of-{logical}"


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


@pytest.fixture
def admin_resolver() -> _ApiStubResolver:
    return _ApiStubResolver()


@pytest_asyncio.fixture
async def admin_client(
    pg_container: str, admin_resolver: _ApiStubResolver
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
    os.environ.setdefault(
        "RAG_API_KEY_DEK",
        "test-api-key-dek-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    )
    os.environ.setdefault("ENVIRONMENT", "dev")

    def _factory(_cfg, app_in):  # type: ignore[no-untyped-def]
        # Le lifespan a déjà branché un `client_provider` "réel" sur
        # `app.state` ; on le remplace par un stub qui retourne toujours
        # le coffre "rag" pour que les routers M5c puissent fonctionner
        # sans table `harpocrate_vaults` peuplée.
        app_in.state.client_provider = _ApiStubClientProvider()
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
