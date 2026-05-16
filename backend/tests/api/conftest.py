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
    os.environ.setdefault("HARPOCRATE_API_TOKEN_RAG", "hrpv_1_stub")
    os.environ.setdefault("HARPOCRATE_API_URL_RAG", "https://vault.example.com")
    os.environ.setdefault(
        "HARPOCRATE_DEK",
        "passphrase-of-at-least-32-characters-long",
    )
    os.environ.setdefault("ENVIRONMENT", "dev")

    app = build_app(
        version="0.2.0",
        git_sha="testsha",
        resolver_factory=lambda _cfg, _app: admin_resolver,  # type: ignore[return-value]
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
