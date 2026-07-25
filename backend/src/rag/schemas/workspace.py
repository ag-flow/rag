from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

_PATH_MAX_LEN = 1024
_CONTENT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB UTF-8
_SOURCE_URL_MAX_LEN = 2048


def _validate_source_url(v: str | None) -> str | None:
    """URL de consultation de l'original : http(s) bien formée, sans vérif d'accès.

    Auto-authentifiante côté caller (jeton éventuel dans l'URL) — stockée telle
    quelle, jamais fetchée par le service."""
    if v is None:
        return v
    if len(v) > _SOURCE_URL_MAX_LEN:
        raise ValueError("source_url_too_long")
    if not (v.startswith("http://") or v.startswith("https://")):
        raise ValueError("source_url_must_be_http")
    return v


_WS_NAME_MAX = 128


class PushRequest(BaseModel):
    # Workspace cible en PARAMÈTRE d'appel (comme les outils MCP), plus dans l'URL.
    workspace: str = Field(..., min_length=1, max_length=_WS_NAME_MAX)
    path: str = Field(..., min_length=1, max_length=_PATH_MAX_LEN)
    content: str = Field(..., min_length=1)

    # Les templates d'appel (docflow…) envoient les champs optionnels en chaîne
    # VIDE plutôt qu'absents : "" = non renseigné. Une strategy vide déclenche
    # ainsi la cascade normale (trigger d'extension → défaut du workspace).
    @field_validator("title", "strategy", "source_url", mode="before")
    @classmethod
    def _empty_string_is_none(cls, v: object) -> object:
        return None if v == "" else v
    title: str | None = Field(default=None, min_length=1, max_length=512)
    # Slug de stratégie (mode service, spec chunking §5) : résolu à l'acceptation
    # dans la bibliothèque du caller puis côté système. 128 = borne des labels
    # dont les slugs sont dérivés.
    strategy: str | None = Field(default=None, min_length=1, max_length=128)
    # URL de consultation de l'original (référence, pas de stockage du contenu).
    source_url: str | None = Field(default=None)
    # Ré-évaluation : force le re-traitement même à contenu/indexeur identiques
    # (bypass du dedup) — pour appliquer une stratégie/modèle modifié.
    force: bool = Field(default=False)

    @field_validator("content")
    @classmethod
    def _content_size(cls, v: str) -> str:
        if len(v.encode("utf-8")) > _CONTENT_MAX_BYTES:
            raise ValueError("content_too_large")
        return v

    @field_validator("source_url")
    @classmethod
    def _source_url(cls, v: str | None) -> str | None:
        return _validate_source_url(v)


class DeleteRequest(BaseModel):
    # Suppression : workspace + path en paramètres d'appel (plus dans l'URL).
    workspace: str = Field(..., min_length=1, max_length=_WS_NAME_MAX)
    path: str = Field(..., min_length=1, max_length=_PATH_MAX_LEN)


class PushAsyncResponse(BaseModel):
    job_id: str
    status: str = "pending"


class DeleteAsyncResponse(BaseModel):
    job_id: str
    status: str = "pending"
