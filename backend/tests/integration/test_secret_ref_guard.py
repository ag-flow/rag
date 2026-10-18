"""Garde des refs de secrets écrites dans une config de service (2026-10-18).

Seuls les coffres modifiables par l'appelant (possédé, ou coffre par défaut)
peuvent être référencés : sinon la clé d'autrui partirait vers un base_url
choisi par l'appelant."""

from __future__ import annotations

import asyncpg
import pytest

from rag.services.secret_ref_guard import ForeignVaultRefError, db_require_writable_vault_refs

_ME = "m" * 64
_OTHER = "o" * 64


@pytest.fixture
async def vaults(migrated: asyncpg.Pool) -> asyncpg.Pool:
    async with migrated.acquire() as conn:
        for name, owner, default in (
            ("mine", _ME, False),
            ("theirs", _OTHER, False),
            ("rag", "", True),
        ):
            await conn.execute(
                "INSERT INTO harpocrate_vaults "
                "(id, name, label, base_url, api_key_id, api_key_encrypted, is_default, owner_id) "
                "VALUES (gen_random_uuid(), $1, $1, 'https://h', $1, "
                "pgp_sym_encrypt('s', 'passphrase-of-at-least-32-characters-long'), $3, $2)",
                name,
                owner,
                default,
            )
    return migrated


async def _check(pool: asyncpg.Pool, *refs: str | None) -> None:
    async with pool.acquire() as conn:
        await db_require_writable_vault_refs(
            conn, owner_id=_ME, refs=list(refs), default_vault_name="rag"
        )


@pytest.mark.asyncio
async def test_own_default_bare_and_empty_refs_are_accepted(vaults: asyncpg.Pool) -> None:
    await _check(vaults, "${vault://mine:/p/openai}", "${vault://rag:/p/x}", "openai_key", None, "")


@pytest.mark.parametrize(
    ("ref", "vault"),
    [
        ("${vault://theirs:/providers/openai}", "theirs"),
        ("${vault://ghost:/providers/openai}", "ghost"),
    ],
)
@pytest.mark.asyncio
async def test_foreign_or_unknown_vault_ref_is_refused(
    vaults: asyncpg.Pool, ref: str, vault: str
) -> None:
    with pytest.raises(ForeignVaultRefError) as exc:
        await _check(vaults, "${vault://mine:/ok}", ref)
    assert exc.value.vault == vault


@pytest.mark.asyncio
async def test_malformed_ref_is_refused(vaults: asyncpg.Pool) -> None:
    with pytest.raises(ForeignVaultRefError):
        await _check(vaults, "${vault://theirs:}")
