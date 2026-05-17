from __future__ import annotations

import re
from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import asyncpg
import pytest

from rag.api.errors import WorkspaceNotFound
from rag.db.helpers import fetch_one
from rag.db.migrations import run_migrations
from rag.schemas.admin import IndexerSpec, WorkspaceCreateRequest
from rag.services.workspaces import create_workspace, rotate_apikey

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
_DEK = "x" * 32


class _Resolver:
    async def resolve_with_retry(self, ref: str) -> str:
        assert re.fullmatch(r"\$\{vault://[^:]+:[^}]+\}", ref)
        return "sk-x"


@pytest.fixture
def cleanup_ws_dbs(pg_container: str) -> Iterator[None]:
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


@pytest.mark.asyncio
async def test_rotate_apikey_returns_new_key_and_updates_encrypted(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"

    create_resp = await create_workspace(
        request=WorkspaceCreateRequest(
            name="ws_rotate",
            indexer=IndexerSpec(provider="openai", model="text-embedding-3-small", api_key_ref="k"),
        ),
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=_Resolver(),  # type: ignore[arg-type]
        default_vault_name="rag",
        api_key_dek=_DEK,
    )
    old_key = create_resp["api_key"]

    new_key = await rotate_apikey(name="ws_rotate", config_pool=session_pool, api_key_dek=_DEK)
    assert new_key != old_key
    assert re.fullmatch(r"[A-Za-z0-9_-]{48}", new_key)

    row = await fetch_one(
        session_pool,
        "SELECT pgp_sym_decrypt(api_key_encrypted, $1::text)::text AS decrypted, "
        "api_key_fingerprint FROM workspaces WHERE name=$2",
        _DEK,
        "ws_rotate",
    )
    assert row is not None
    assert row["decrypted"] == new_key
    assert row["api_key_fingerprint"] == sha256(new_key.encode()).hexdigest()
    # L'ancienne clé ne doit plus correspondre
    assert row["decrypted"] != old_key


@pytest.mark.asyncio
async def test_rotate_apikey_workspace_not_found(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    with pytest.raises(WorkspaceNotFound):
        await rotate_apikey(name="absent", config_pool=session_pool, api_key_dek=_DEK)


@pytest.mark.asyncio
async def test_rotate_handles_fingerprint_collision(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    """La boucle anti-collision gère le cas où la clé générée a un fingerprint déjà pris.

    Scénario : generate_api_key retourne "k_collide" les 2 premières fois,
    puis "k_ok" (fingerprint distinct). Un workspace tiers possède déjà le
    fingerprint de "k_collide". rotate_apikey ne doit pas lever et doit
    retourner "k_ok".
    """
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"

    # Workspace cible de la rotation
    await create_workspace(
        request=WorkspaceCreateRequest(
            name="ws_col_target",
            indexer=IndexerSpec(provider="openai", model="text-embedding-3-small", api_key_ref="k"),
        ),
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=_Resolver(),  # type: ignore[arg-type]
        default_vault_name="rag",
        api_key_dek=_DEK,
    )

    # Workspace tiers dont le fingerprint = sha256("k_collide")
    # On l'insère directement avec seed_workspace pour éviter la création de BDD
    from tests.integration._workspace_seed import seed_workspace
    async with session_pool.acquire() as conn:
        await seed_workspace(
            conn,
            name="ws_col_blocker",
            api_key="k_collide",
            dek=_DEK,
            rag_cnx="postgresql://test/blocker",
            rag_base="rag_test_blocker",
        )

    keys_iter = iter(["k_collide", "k_collide", "k_ok"])
    with patch("rag.services.workspaces.generate_api_key", side_effect=lambda: next(keys_iter)):
        result = await rotate_apikey(
            name="ws_col_target", config_pool=session_pool, api_key_dek=_DEK
        )

    assert result == "k_ok"
    row = await fetch_one(
        session_pool,
        "SELECT pgp_sym_decrypt(api_key_encrypted, $1::text)::text AS decrypted "
        "FROM workspaces WHERE name=$2",
        _DEK,
        "ws_col_target",
    )
    assert row is not None
    assert row["decrypted"] == "k_ok"
