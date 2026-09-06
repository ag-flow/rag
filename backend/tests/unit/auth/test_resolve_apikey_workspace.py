"""Split 401/404 sur la résolution de workspace par clé API.

Décision architecte (2026-09-06) : le 401 uniforme mélangeait « problème de
sécurité » et « workspace inconnu », rendant le diagnostic impossible (une
campagne d'events docflow vers un workspace jamais créé a été investiguée
comme un problème d'autorisation). Désormais :

- 401 = sécurité : clé invalide ou niveau (scope) insuffisant ;
- 404 `workspace_not_found` = le workspace demandé n'est pas disponible pour
  cette clé — inexistant OU possédé par autrui (on ne révèle jamais
  l'existence du workspace d'un autre owner).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from rag.auth.workspace_auth import (
    resolve_apikey_read_workspace,
    resolve_apikey_write_workspace,
)

_OWNER = "a" * 64


def _request(pool) -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(pools=SimpleNamespace(config_pool=pool)))
    )


def _pool(*, ws_row: dict | None, ws_exists_for_someone: bool) -> MagicMock:
    """`fetchrow` = lookup owner-scopé ; `fetchval` = existence toutes visibilités."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=ws_row)
    pool.fetchval = AsyncMock(return_value=1 if ws_exists_for_someone else None)
    return pool


_WRITE_ROW = {"id": uuid4(), "indexer_used": "openai/text-embedding-3-small"}
_READ_ROW = {"id": uuid4(), "name": "ws", "rag_cnx": "postgresql://x/rag_ws"}


class TestWriteResolution:
    @pytest.mark.asyncio
    async def test_insufficient_scope_is_401_security(self) -> None:
        pool = _pool(ws_row=_WRITE_ROW, ws_exists_for_someone=True)
        with pytest.raises(HTTPException) as exc:
            await resolve_apikey_write_workspace(
                _request(pool), owner_id=_OWNER, scope="read", workspace="ws"
            )
        assert exc.value.status_code == 401
        assert exc.value.detail == "insufficient_scope"
        # La sécurité se juge AVANT tout accès base : pas de fuite d'existence.
        pool.fetchrow.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_workspace_is_404(self) -> None:
        pool = _pool(ws_row=None, ws_exists_for_someone=False)
        with pytest.raises(HTTPException) as exc:
            await resolve_apikey_write_workspace(
                _request(pool), owner_id=_OWNER, scope="read_write", workspace="ghost"
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "workspace_not_found"

    @pytest.mark.asyncio
    async def test_foreign_workspace_is_404_not_401(self) -> None:
        """Le workspace d'autrui reste INTROUVABLE — un 401 révélerait son existence."""
        pool = _pool(ws_row=None, ws_exists_for_someone=True)
        with pytest.raises(HTTPException) as exc:
            await resolve_apikey_write_workspace(
                _request(pool), owner_id=_OWNER, scope="read_write", workspace="ws_autrui"
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "workspace_not_found"

    @pytest.mark.asyncio
    async def test_visible_workspace_resolves(self) -> None:
        pool = _pool(ws_row=_WRITE_ROW, ws_exists_for_someone=True)
        ctx = await resolve_apikey_write_workspace(
            _request(pool), owner_id=_OWNER, scope="admin", workspace="ws"
        )
        assert ctx.workspace_id == _WRITE_ROW["id"]
        assert ctx.owner_id == _OWNER


class TestReadResolution:
    @pytest.mark.asyncio
    async def test_unknown_workspace_is_404(self) -> None:
        pool = _pool(ws_row=None, ws_exists_for_someone=False)
        with pytest.raises(HTTPException) as exc:
            await resolve_apikey_read_workspace(
                _request(pool), owner_id=_OWNER, scope="read", workspace="ghost"
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "workspace_not_found"

    @pytest.mark.asyncio
    async def test_foreign_workspace_is_404_not_401(self) -> None:
        pool = _pool(ws_row=None, ws_exists_for_someone=True)
        with pytest.raises(HTTPException) as exc:
            await resolve_apikey_read_workspace(
                _request(pool), owner_id=_OWNER, scope="read", workspace="ws_autrui"
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "workspace_not_found"

    @pytest.mark.asyncio
    async def test_visible_workspace_resolves(self) -> None:
        pool = _pool(ws_row=_READ_ROW, ws_exists_for_someone=True)
        ctx = await resolve_apikey_read_workspace(
            _request(pool), owner_id=_OWNER, scope="read", workspace="ws"
        )
        assert ctx.workspace_name == "ws"
        assert ctx.scope == "read"
