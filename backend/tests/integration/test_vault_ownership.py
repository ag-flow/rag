from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.auth.owner import email_to_owner_id
from rag.config import Settings
from rag.db.migrations import run_migrations
from rag.schemas.harpocrate_vaults import VaultCreateRequest
from rag.services.harpocrate_vaults import HarpocrateVaultsService

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _set_required_env(monkeypatch) -> None:
    """Set les champs requis de Settings + une DEK valide pour les tests."""
    monkeypatch.setenv("RAG_MASTER_KEY", "x" * 64)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@localhost:5432/postgres")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("HARPOCRATE_DEK", "passphrase-of-at-least-32-characters-long")


def _create_req(name: str, is_default: bool = False, **overrides) -> VaultCreateRequest:
    """Helper pour créer une VaultCreateRequest avec valeurs par défaut."""
    payload = {
        "name": name,
        "label": name,
        "base_url": "https://harpocrate.yoops.org",
        "api_key_id": "k-001",
        "api_key": "supersecretvalue123",
        "is_default": is_default,
    }
    payload.update(overrides)
    return VaultCreateRequest(**payload)


@pytest.mark.asyncio
async def test_create_sets_owner_id(session_pool: asyncpg.Pool, monkeypatch) -> None:
    """Vérifier que create() enregistre l'owner_id fourni."""
    _set_required_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    owner_id = email_to_owner_id("alice@example.com")

    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        async with conn.transaction():
            v = await svc.create(conn, _create_req("v-alice"), owner_id=owner_id)

    assert v.owner_id == owner_id


@pytest.mark.asyncio
async def test_list_for_owner_shows_own_and_default(
    session_pool: asyncpg.Pool, monkeypatch
) -> None:
    """list_for_owner() retourne les coffres propres + les defaults partagés."""
    _set_required_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())

    owner_alice = email_to_owner_id("alice@example.com")
    owner_bob = email_to_owner_id("bob@example.com")

    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        async with conn.transaction():
            await svc.create(
                conn, _create_req("default-v", is_default=True), owner_id=owner_alice
            )
            await svc.create(conn, _create_req("alice-v"), owner_id=owner_alice)
            await svc.create(conn, _create_req("bob-v"), owner_id=owner_bob)

    async with session_pool.acquire() as conn:
        alice_vaults = await svc.list_for_owner(conn, owner_alice)
    assert {v.name for v in alice_vaults} == {"default-v", "alice-v"}

    async with session_pool.acquire() as conn:
        bob_vaults = await svc.list_for_owner(conn, owner_bob)
    assert {v.name for v in bob_vaults} == {"default-v", "bob-v"}


@pytest.mark.asyncio
async def test_list_for_owner_default_visible_to_all(
    session_pool: asyncpg.Pool, monkeypatch
) -> None:
    """Les coffres is_default=True sont visibles par tous les propriétaires."""
    _set_required_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())

    owner_alice = email_to_owner_id("alice@example.com")
    owner_carol = email_to_owner_id("carol@example.com")

    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        async with conn.transaction():
            await svc.create(
                conn, _create_req("shared-default", is_default=True), owner_id=owner_alice
            )

    async with session_pool.acquire() as conn:
        carol_vaults = await svc.list_for_owner(conn, owner_carol)
    assert len(carol_vaults) == 1
    assert carol_vaults[0].name == "shared-default"
