from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import asyncpg
import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
def pg_container() -> Iterator[str]:
    """Spawn un Postgres + pgvector éphémère pour toute la session de tests.

    Yield le DSN asyncpg-compatible (postgresql://...).
    """
    with PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="rag",
        password="ragpass",
        dbname="rag_config",
    ) as pg:
        dsn = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
        yield dsn


@pytest_asyncio.fixture(scope="session")
async def session_pool(pg_container: str) -> AsyncIterator[asyncpg.Pool]:
    """Un pool partagé pour la session, sur la base `rag_config` du container."""
    pool = await asyncpg.create_pool(pg_container, min_size=1, max_size=4)
    try:
        yield pool
    finally:
        await pool.close()
