from __future__ import annotations

import asyncio
import re
from pathlib import Path

import asyncpg
import structlog

log = structlog.get_logger(__name__)

VERSIONS_DIR = Path(__file__).parent / "versions"
_FILENAME_RE = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")


def _list_versions() -> list[tuple[int, Path]]:
    """Retourne [(version, path)] triés par version croissante (I/O bloquante)."""
    out: list[tuple[int, Path]] = []
    for p in sorted(VERSIONS_DIR.iterdir()):
        if not p.is_file():
            continue
        m = _FILENAME_RE.match(p.name)
        if not m:
            raise RuntimeError(
                f"workspace migration filename does not match NNN_description.sql: {p.name}"
            )
        out.append((int(m.group(1)), p))
    return out


def _read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


async def apply_pending(workspace_dsn: str) -> int:
    """Applique les migrations workspace manquantes sur `workspace_dsn`.

    Idempotent. Crée `workspace_schema_migrations` si absente, lit la version
    courante, applique en ordre numérique les migrations > version courante.
    Chaque migration s'exécute dans sa propre transaction : si elle échoue, la
    transaction est rollback ET l'exception remonte (fail-fast). Les migrations
    précédentes restent appliquées.

    Retourne le nombre de migrations appliquées dans cet appel.
    """
    conn = await asyncpg.connect(workspace_dsn)
    try:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS workspace_schema_migrations ("
            "version INT PRIMARY KEY, "
            "applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        current = await conn.fetchval(
            "SELECT COALESCE(MAX(version), 0) FROM workspace_schema_migrations"
        )

        versions = await asyncio.to_thread(_list_versions)
        pending = [(v, p) for v, p in versions if v > current]

        applied_count = 0
        for version, path in pending:
            sql = await asyncio.to_thread(_read_sql, path)
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO workspace_schema_migrations (version) VALUES ($1)",
                    version,
                )
            log.info("workspace_migration.applied", version=version, file=path.name)
            applied_count += 1

        return applied_count
    finally:
        await conn.close()
