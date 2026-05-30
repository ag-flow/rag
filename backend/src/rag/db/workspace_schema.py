from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import structlog

log = structlog.get_logger(__name__)


_DBNAME_REGEX = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")


def _validate_dbname(dbname: str) -> None:
    """Défense en profondeur : valide la forme du nom de base avant interpolation SQL.

    Bien que la couche service valide déjà via Pydantic, ce module expose des
    fonctions publiques susceptibles d'être appelées directement — on garde
    donc une garde locale stricte.
    """
    if not _DBNAME_REGEX.fullmatch(dbname):
        raise ValueError(f"invalid dbname {dbname!r}: must match [a-z][a-z0-9_-]{{0,62}}$")


def derive_workspace_dsn(admin_dsn: str, dbname: str) -> str:
    """Construit le DSN de la base workspace à partir du DSN admin (path → /<dbname>).

    Préserve scheme, netloc, query et fragment du DSN admin — uniquement la
    base cible change. Ex. : `?sslmode=require` est conservé.
    """
    parts = urlsplit(admin_dsn)
    return urlunsplit(parts._replace(path=f"/{dbname}"))


async def create_workspace_database(admin_dsn: str, dbname: str) -> None:
    """`CREATE DATABASE "<dbname>"` via le DSN admin.

    Lève `asyncpg.DuplicateDatabaseError` si la base existe déjà — la couche
    appelante (service) décide si c'est une erreur métier (WorkspaceAlreadyExists)
    ou un état acceptable (compensation après crash).

    Le nom est interpolé en SQL (quoting `"<dbname>"`) parce qu'asyncpg
    n'accepte pas de paramètre bindé pour un identifiant DDL. `dbname` provient
    de la validation Pydantic (regex stricte), pas d'une entrée utilisateur libre.
    """
    _validate_dbname(dbname)
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(f'CREATE DATABASE "{dbname}"')
        log.info("workspace.database.created", dbname=dbname)
    finally:
        await conn.close()


async def drop_workspace_database(admin_dsn: str, dbname: str) -> None:
    """`DROP DATABASE IF EXISTS "<dbname>" WITH (FORCE)` via le DSN admin.

    Idempotent : ne lève rien si la base n'existe pas. `WITH (FORCE)` ferme
    les connexions actives (utile dès M3/M4).
    """
    _validate_dbname(dbname)
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        log.info("workspace.database.dropped", dbname=dbname)
    finally:
        await conn.close()


async def create_embeddings_table(workspace_dsn: str, *, dimension: int) -> None:
    """Active l'extension `vector` + crée la table `embeddings(vector(N))` + index ivfflat.

    `dimension` est résolue depuis `model_dimensions` au niveau service.
    Lève toute erreur asyncpg : la couche appelante gère la compensation
    (drop database si la création du schéma échoue).
    """
    if dimension <= 0:
        raise ValueError(f"dimension must be > 0, got {dimension}")

    conn = await asyncpg.connect(workspace_dsn)
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(
            f"""
            CREATE TABLE embeddings (
                id           SERIAL PRIMARY KEY,
                path         TEXT NOT NULL,
                chunk_index  INT  NOT NULL,
                content      TEXT NOT NULL,
                embedding    vector({dimension}) NOT NULL,
                metadata     JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                indexed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (path, chunk_index)
            )
            """
        )
        # ivfflat est limité à 2000 dimensions — utiliser hnsw au-delà.
        if dimension <= 2000:
            await conn.execute(
                "CREATE INDEX ON embeddings USING ivfflat (embedding vector_cosine_ops)"
            )
        else:
            await conn.execute(
                "CREATE INDEX ON embeddings USING hnsw (embedding vector_cosine_ops)"
            )
        log.info("workspace.embeddings.created", dimension=dimension)
    finally:
        await conn.close()
