from __future__ import annotations

import json

import asyncpg
import structlog

from rag.schemas.enrichments import PromptTemplateCreate, PromptTemplateOut, PromptTemplatePatch

log = structlog.get_logger(__name__)


class TemplateNotFoundError(Exception):
    """Template inexistant ou invisible pour cet utilisateur."""


class TemplateImmutableError(Exception):
    """Template système : visible de tous, ni éditable ni supprimable."""


class TemplateInUseError(Exception):
    """Suppression refusée : le template est référencé par des triggers."""

    def __init__(self, used_by_triggers: int) -> None:
        self.used_by_triggers = used_by_triggers
        super().__init__(f"template utilisé par {used_by_triggers} trigger(s)")


class InvalidLanguageError(Exception):
    """Langue inconnue du référentiel `languages` (codes BCP 47, spec 14)."""

    def __init__(self, language: str, valid_codes: list[str]) -> None:
        self.language = language
        self.valid_codes = valid_codes
        super().__init__(f"langue inconnue : {language!r}")


# Portée bibliothèque (spec chunking §4, S3.3) : templates système (owner
# NULL) + ceux de l'utilisateur. Le binding des triggers reste PAR ID.
# Fragments SQL statiques (aucun input utilisateur) — les noqa S608 couvrent
# uniquement leur interpolation.
_OUT_COLUMNS = """
    t.id, t.name, t.language, t.description, t.metadata_key, t.result_type,
    t.result_schema, t.prompt, t.target, t.timing, t.prompt_version,
    (t.owner_id IS NULL) AS is_system,
    (SELECT count(*) FROM workspace_extension_trigger_prompts p
       WHERE p.template_id = t.id)::int AS used_by_triggers,
    (SELECT count(*) FROM chunking_strategy_prompts sp
       WHERE sp.template_id = t.id)::int AS used_by_strategies,
    t.created_at, t.updated_at
"""
_VISIBLE = "(t.owner_id IS NULL OR t.owner_id = $1)"


def _to_out(row: asyncpg.Record) -> PromptTemplateOut:
    data = dict(row)
    if isinstance(data["result_schema"], str):
        data["result_schema"] = json.loads(data["result_schema"])
    return PromptTemplateOut.model_validate(data)


async def list_prompt_templates(
    conn: asyncpg.Connection, *, owner_id: str
) -> list[PromptTemplateOut]:
    rows = await conn.fetch(
        f"SELECT {_OUT_COLUMNS} FROM prompt_templates t WHERE {_VISIBLE} "  # noqa: S608
        "ORDER BY t.language, t.name",
        owner_id,
    )
    return [_to_out(r) for r in rows]


async def get_prompt_template(
    conn: asyncpg.Connection, *, owner_id: str, template_id: str
) -> PromptTemplateOut | None:
    row = await conn.fetchrow(
        f"SELECT {_OUT_COLUMNS} FROM prompt_templates t "  # noqa: S608
        f"WHERE {_VISIBLE} AND t.id = $2::uuid",
        owner_id,
        template_id,
    )
    return _to_out(row) if row else None


async def _validate_language(conn: asyncpg.Connection, language: str) -> None:
    """`language` doit exister dans le référentiel `languages` (codes BCP 47).

    L'IHM contraint déjà la saisie par un sélecteur ; les surfaces
    programmatiques (MCP, REST direct) passaient n'importe quelle valeur
    ('markdown'…) — la règle vit ici, partagée par tous les canaux."""
    known = await conn.fetchval("SELECT 1 FROM languages WHERE code = $1", language)
    if known is None:
        codes = [r["code"] for r in await conn.fetch("SELECT code FROM languages ORDER BY code")]
        raise InvalidLanguageError(language, codes)


async def create_prompt_template(
    conn: asyncpg.Connection, *, owner_id: str, req: PromptTemplateCreate
) -> PromptTemplateOut:
    await _validate_language(conn, req.language)
    template_id = await conn.fetchval(
        "INSERT INTO prompt_templates "
        "(owner_id, name, language, description, metadata_key, result_type, "
        " result_schema, prompt, target, timing) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10) RETURNING id",
        owner_id,
        req.name,
        req.language,
        req.description,
        req.metadata_key,
        req.result_type,
        json.dumps(req.result_schema) if req.result_schema else None,
        req.prompt,
        req.target,
        req.timing,
    )
    log.info("prompt_template.created", name=req.name)
    result = await get_prompt_template(conn, owner_id=owner_id, template_id=str(template_id))
    if result is None:  # pragma: no cover — la ligne vient d'être insérée
        raise RuntimeError("create_prompt_template: inserted row not found")
    return result


async def _fetch_owned(
    conn: asyncpg.Connection, *, owner_id: str, template_id: str
) -> asyncpg.Record:
    """Charge un template pour modification : le sien uniquement.

    Système → immutable ; inexistant ou d'un autre user → introuvable.
    """
    row = await conn.fetchrow(
        "SELECT t.id, t.owner_id FROM prompt_templates t "  # noqa: S608
        f"WHERE {_VISIBLE} AND t.id = $2::uuid FOR UPDATE",
        owner_id,
        template_id,
    )
    if row is None:
        raise TemplateNotFoundError(template_id)
    if row["owner_id"] is None:
        raise TemplateImmutableError(template_id)
    return row


async def patch_prompt_template(
    conn: asyncpg.Connection, *, owner_id: str, template_id: str, req: PromptTemplatePatch
) -> PromptTemplateOut:
    async with conn.transaction():
        await _fetch_owned(conn, owner_id=owner_id, template_id=template_id)
        # prompt_version invalide le cache de contexte (spec « Prompt B ») :
        # bump automatique dès que le TEXTE du prompt change réellement.
        await conn.execute(
            "UPDATE prompt_templates SET "
            "description = COALESCE($2, description), "
            "prompt_version = prompt_version + "
            "  CASE WHEN $3::text IS NOT NULL AND $3::text <> prompt THEN 1 ELSE 0 END, "
            "prompt = COALESCE($3, prompt), "
            "result_schema = COALESCE($4::jsonb, result_schema), "
            "updated_at = now() "
            "WHERE id = $1::uuid",
            template_id,
            req.description,
            req.prompt,
            json.dumps(req.result_schema) if req.result_schema else None,
        )
    result = await get_prompt_template(conn, owner_id=owner_id, template_id=template_id)
    if result is None:  # pragma: no cover — verrouillé par _fetch_owned
        raise TemplateNotFoundError(template_id)
    return result


async def delete_prompt_template(
    conn: asyncpg.Connection, *, owner_id: str, template_id: str
) -> None:
    """Supprime un template de l'utilisateur, refusé s'il est référencé."""
    async with conn.transaction():
        await _fetch_owned(conn, owner_id=owner_id, template_id=template_id)
        ref_count = await conn.fetchval(
            "SELECT (SELECT count(*) FROM workspace_extension_trigger_prompts "
            "        WHERE template_id = $1::uuid) "
            "     + (SELECT count(*) FROM chunking_strategy_prompts "
            "        WHERE template_id = $1::uuid)",
            template_id,
        )
        if int(ref_count or 0) > 0:
            raise TemplateInUseError(int(ref_count))
        await conn.execute("DELETE FROM prompt_templates WHERE id = $1::uuid", template_id)
    log.info("prompt_template.deleted", template_id=template_id)
