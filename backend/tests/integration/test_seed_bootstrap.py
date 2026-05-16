from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.config import Settings
from rag.db.migrations import run_migrations
from rag.schemas.harpocrate_vaults import VaultCreateRequest
from rag.secrets.bootstrap import seed_vaults_from_env_if_empty
from rag.services.harpocrate_vaults import HarpocrateVaultsService

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _set_base_env(monkeypatch) -> None:
    monkeypatch.setenv("RAG_MASTER_KEY", "x" * 64)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@localhost:5432/postgres")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    # purge éventuelles paires Harpocrate de l'env
    monkeypatch.delenv("HARPOCRATE_API_TOKEN_RAG", raising=False)
    monkeypatch.delenv("HARPOCRATE_API_URL_RAG", raising=False)
    monkeypatch.delenv("HARPOCRATE_DEK", raising=False)


@pytest.mark.asyncio
async def test_seed_creates_vault_named_rag(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    _set_base_env(monkeypatch)
    monkeypatch.setenv(
        "HARPOCRATE_DEK",
        "passphrase-of-at-least-32-characters-long",
    )
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "envsecret")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://h.env")
    await run_migrations(session_pool, MIGRATIONS_DIR)
    settings = Settings()
    svc = HarpocrateVaultsService(settings)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")

    count = await seed_vaults_from_env_if_empty(
        settings=settings,
        pool=session_pool,
        vaults_service=svc,
    )
    assert count == 1
    async with session_pool.acquire() as conn:
        v = await svc.get_by_name(conn, "rag")
    assert v is not None
    assert v.is_default is True
    # Pydantic Settings normalise les noms d'env vars en lowercase → identifier='rag'
    assert v.api_key_id == "env:rag"


@pytest.mark.asyncio
async def test_seed_skipped_when_db_non_empty(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    _set_base_env(monkeypatch)
    monkeypatch.setenv(
        "HARPOCRATE_DEK",
        "passphrase-of-at-least-32-characters-long",
    )
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "envsecret")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://h.env")
    await run_migrations(session_pool, MIGRATIONS_DIR)
    settings = Settings()
    svc = HarpocrateVaultsService(settings)
    # Préseed avec un coffre différent
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        async with conn.transaction():
            await svc.create(
                conn,
                VaultCreateRequest(
                    name="existing",
                    label="X",
                    base_url="https://x.example",
                    api_key_id="k1",
                    api_key="secret12345678",
                    is_default=True,
                ),
            )

    count = await seed_vaults_from_env_if_empty(
        settings=settings,
        pool=session_pool,
        vaults_service=svc,
    )
    assert count == 0


@pytest.mark.asyncio
async def test_seed_skipped_when_env_empty(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    _set_base_env(monkeypatch)
    monkeypatch.setenv(
        "HARPOCRATE_DEK",
        "passphrase-of-at-least-32-characters-long",
    )
    # pas de HARPOCRATE_API_TOKEN_*
    await run_migrations(session_pool, MIGRATIONS_DIR)
    settings = Settings()
    svc = HarpocrateVaultsService(settings)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")

    count = await seed_vaults_from_env_if_empty(
        settings=settings,
        pool=session_pool,
        vaults_service=svc,
    )
    assert count == 0


@pytest.mark.asyncio
async def test_seed_aborted_when_dek_missing(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    _set_base_env(monkeypatch)
    # HARPOCRATE_DEK volontairement absent
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "envsecret")
    monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://h.env")
    await run_migrations(session_pool, MIGRATIONS_DIR)
    settings = Settings()
    svc = HarpocrateVaultsService(settings)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")

    count = await seed_vaults_from_env_if_empty(
        settings=settings,
        pool=session_pool,
        vaults_service=svc,
    )
    assert count == 0
