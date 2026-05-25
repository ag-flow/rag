from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

import asyncpg


async def fetch_one(pool: asyncpg.Pool, query: str, *args: Any) -> asyncpg.Record | None:
    """Exécute la requête et retourne la première ligne (ou None)."""
    async with pool.acquire() as conn:
        return cast("asyncpg.Record | None", await conn.fetchrow(query, *args))


async def fetch_all(pool: asyncpg.Pool, query: str, *args: Any) -> list[asyncpg.Record]:
    """Exécute la requête et retourne toutes les lignes."""
    async with pool.acquire() as conn:
        return cast("list[asyncpg.Record]", await conn.fetch(query, *args))


async def execute(pool: asyncpg.Pool, query: str, *args: Any) -> str:
    """Exécute la requête (INSERT/UPDATE/DELETE/DDL), retourne le tag asyncpg."""
    async with pool.acquire() as conn:
        return cast("str", await conn.execute(query, *args))


@asynccontextmanager
async def transaction(pool: asyncpg.Pool) -> AsyncIterator[asyncpg.Connection]:
    """Context manager qui ouvre une connexion + une transaction.

    Usage :
        async with transaction(pool) as conn:
            await conn.execute(...)
            await conn.execute(...)

    Rollback automatique si une exception est levée.
    """
    async with pool.acquire() as conn, conn.transaction():
        yield conn
