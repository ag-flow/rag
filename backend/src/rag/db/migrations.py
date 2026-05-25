from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg
import structlog

log = structlog.get_logger(__name__)


class MigrationError(RuntimeError):
    """Une migration SQL a échoué — état de la base : préservé jusqu'à la dernière migration OK."""


def _list_sql_files(migrations_dir: Path) -> list[Path]:
    """Énumère les fichiers `.sql` du dossier, triés alphabétiquement (I/O bloquante)."""
    return sorted(p for p in migrations_dir.iterdir() if p.suffix == ".sql")


def _read_sql(path: Path) -> str:
    """Lit le contenu d'une migration (I/O bloquante)."""
    return path.read_text(encoding="utf-8")


async def run_migrations(pool: asyncpg.Pool, migrations_dir: Path) -> None:
    """Applique toutes les migrations `.sql` du dossier non encore appliquées.

    Convention :
    - Fichiers nommés `NNN_description.sql`, triés alphabétiquement.
    - La version stockée dans `schema_migrations.version` est le nom sans `.sql`.
    - La migration `000_schema_migrations.sql` crée la table de suivi elle-même —
      elle est appliquée systématiquement en premier (idempotent).
    - Une migration KO interrompt le runner et lève `MigrationError`.

    Les accès disque (listing + lecture des `.sql`) sont délégués à `asyncio.to_thread`
    pour ne pas bloquer la boucle événementielle.
    """
    files = await asyncio.to_thread(_list_sql_files, migrations_dir)
    if not files:
        log.info("migrations.empty", dir=str(migrations_dir))
        return

    bootstrap = next((f for f in files if f.name.startswith("000_")), None)
    if bootstrap is None:
        raise MigrationError("Missing 000_schema_migrations.sql bootstrap file")

    bootstrap_sql = await asyncio.to_thread(_read_sql, bootstrap)

    async with pool.acquire() as conn:
        await conn.execute(bootstrap_sql)
        await conn.execute(
            "INSERT INTO schema_migrations (version) VALUES ($1) ON CONFLICT (version) DO NOTHING",
            bootstrap.stem,
        )

        applied = {
            row["version"] for row in await conn.fetch("SELECT version FROM schema_migrations")
        }

        for f in files:
            if f.name.startswith("000_"):
                continue
            version = f.stem
            if version in applied:
                log.debug("migrations.skip", version=version)
                continue

            sql = await asyncio.to_thread(_read_sql, f)
            log.info("migrations.apply", version=version)
            try:
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES ($1)",
                        version,
                    )
            except asyncpg.PostgresError as e:
                raise MigrationError(f"Migration {version} failed: {e}") from e


async def list_applied(pool: asyncpg.Pool) -> list[str]:
    """Retourne la liste des versions appliquées, triées."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT version FROM schema_migrations ORDER BY version")
    return [r["version"] for r in rows]
