"""Isolation inter-utilisateurs des templates de prompts (service owner-scoped).

Toute primitive MCP identifie l'utilisateur (owner_id, humain via OBO ou clé) :
la lecture/modification d'un template d'AUTRUI est refusée, et la création
attribue le template au caller. Les templates système (owner NULL) sont
partagés en lecture et immuables.
"""

from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.schemas.enrichments import PromptTemplateCreate, PromptTemplatePatch
from rag.services import prompt_templates as svc

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

OWNER_A = "a" * 64
OWNER_B = "b" * 64


async def _conn(session_pool: asyncpg.Pool) -> asyncpg.Connection:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    return await session_pool.acquire()


def _create(name: str) -> PromptTemplateCreate:
    return PromptTemplateCreate(
        name=name,
        language="fr-FR",
        metadata_key="summary",
        prompt="Résume : {content}",
        target="document",
        timing="post_index_metadata",
    )


@pytest.mark.asyncio
async def test_create_attributes_to_caller_and_scopes_list(session_pool: asyncpg.Pool) -> None:
    conn = await _conn(session_pool)
    try:
        await svc.create_prompt_template(conn, owner_id=OWNER_A, req=_create("tmpl-a"))
        await svc.create_prompt_template(conn, owner_id=OWNER_B, req=_create("tmpl-b"))

        names_a = {t.name for t in await svc.list_prompt_templates(conn, owner_id=OWNER_A)}
        assert "tmpl-a" in names_a
        assert "tmpl-b" not in names_a  # le template de B n'apparaît pas chez A
    finally:
        await session_pool.release(conn)


@pytest.mark.asyncio
async def test_other_owner_template_invisible_and_immutable(session_pool: asyncpg.Pool) -> None:
    conn = await _conn(session_pool)
    try:
        owned_by_b = await svc.create_prompt_template(
            conn, owner_id=OWNER_B, req=_create("privee-b")
        )
        tid = str(owned_by_b.id)

        # Lecture : invisible pour A.
        assert await svc.get_prompt_template(conn, owner_id=OWNER_A, template_id=tid) is None
        # Modification / suppression : refusées (introuvable pour A).
        with pytest.raises(svc.TemplateNotFoundError):
            await svc.patch_prompt_template(
                conn, owner_id=OWNER_A, template_id=tid, req=PromptTemplatePatch(prompt="vol")
            )
        with pytest.raises(svc.TemplateNotFoundError):
            await svc.delete_prompt_template(conn, owner_id=OWNER_A, template_id=tid)
        # B conserve l'accès.
        assert await svc.get_prompt_template(conn, owner_id=OWNER_B, template_id=tid) is not None
    finally:
        await session_pool.release(conn)


@pytest.mark.asyncio
async def test_create_rejects_unknown_language(session_pool: asyncpg.Pool) -> None:
    """`language` doit être un code BCP 47 du référentiel — 'markdown' est invalide.

    La règle vit au service : REST et MCP la partagent (bug : le MCP laissait
    passer n'importe quelle valeur)."""
    conn = await _conn(session_pool)
    try:
        req = _create("tmpl-bad-lang")
        req = req.model_copy(update={"language": "markdown"})
        with pytest.raises(svc.InvalidLanguageError) as exc_info:
            await svc.create_prompt_template(conn, owner_id=OWNER_A, req=req)
        assert exc_info.value.language == "markdown"
        assert "fr-FR" in exc_info.value.valid_codes

        # Le message MCP (explain) est actionnable : il liste les codes valides.
        from rag.api.mcp_library_support import explain

        msg = explain(exc_info.value)
        assert "markdown" in msg
        assert "fr-FR" in msg
    finally:
        await session_pool.release(conn)
