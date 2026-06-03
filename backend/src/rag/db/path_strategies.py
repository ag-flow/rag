from __future__ import annotations

from typing import Literal
from uuid import UUID

import asyncpg
import structlog

log = structlog.get_logger(__name__)


async def get_strategy(
    pool: asyncpg.Pool,
    workspace_id: UUID,
    path: str,
) -> Literal["replace", "append"]:
    row = await pool.fetchrow(
        "SELECT strategy FROM path_strategies WHERE workspace_id=$1 AND path=$2",
        workspace_id,
        path,
    )
    if row is None:
        return "replace"
    return row["strategy"]  # type: ignore[return-value]


async def upsert_strategy(
    pool: asyncpg.Pool,
    workspace_id: UUID,
    path: str,
    strategy: Literal["replace", "append"],
    updated_by: Literal["ui", "strategy_file"] = "ui",
) -> None:
    await pool.execute(
        """
        INSERT INTO path_strategies (workspace_id, path, strategy, updated_by, updated_at)
        VALUES ($1, $2, $3, $4, now())
        ON CONFLICT (workspace_id, path) DO UPDATE
        SET strategy=EXCLUDED.strategy, updated_by=EXCLUDED.updated_by, updated_at=now()
        """,
        workspace_id,
        path,
        strategy,
        updated_by,
    )
    log.debug(
        "path_strategies.upserted",
        workspace_id=str(workspace_id),
        path=path,
        strategy=strategy,
        updated_by=updated_by,
    )


async def upsert_strategies_batch(
    pool: asyncpg.Pool,
    workspace_id: UUID,
    strategies: dict[str, Literal["replace", "append"]],
    updated_by: Literal["ui", "strategy_file"] = "strategy_file",
) -> None:
    if not strategies:
        return
    records = [(workspace_id, path, strategy, updated_by) for path, strategy in strategies.items()]
    async with pool.acquire() as conn, conn.transaction():
        await conn.executemany(
            """
            INSERT INTO path_strategies (workspace_id, path, strategy, updated_by, updated_at)
            VALUES ($1, $2, $3, $4, now())
            ON CONFLICT (workspace_id, path) DO UPDATE
            SET strategy=EXCLUDED.strategy, updated_by=EXCLUDED.updated_by, updated_at=now()
            """,
            records,
        )
    log.info(
        "path_strategies.batch_upserted",
        workspace_id=str(workspace_id),
        count=len(strategies),
    )


async def get_all_for_workspace(
    pool: asyncpg.Pool,
    workspace_id: UUID,
) -> dict[str, dict]:
    rows = await pool.fetch(
        """
        SELECT path, strategy, updated_by, updated_at
        FROM path_strategies
        WHERE workspace_id=$1
        """,
        workspace_id,
    )
    return {r["path"]: dict(r) for r in rows}
