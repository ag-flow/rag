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


class PushRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=_PATH_MAX_LEN)
    content: str = Field(..., min_length=1)
    title: str | None = Field(default=None, min_length=1, max_length=512)
    # Slug de stratégie (mode service, spec chunking §5) : résolu à l'acceptation
    # dans la bibliothèque du caller puis côté système. 128 = borne des labels
    # dont les slugs sont dérivés.
    strategy: str | None = Field(default=None, min_length=1, max_length=128)
    # URL de consultation de l'original (référence, pas de stockage du contenu).
    source_url: str | None = Field(default=None)

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


class ReindexRequest(BaseModel):
    """Ré-évaluation d'un document déjà poussé — le path vient de l'URL.

    L'appelant renvoie le contenu (aucun stockage source côté service) ; le
    re-traitement est forcé même si le contenu est identique, pour appliquer une
    stratégie de chunking ou un modèle d'embedding qui a changé depuis.
    """

    content: str = Field(..., min_length=1)
    title: str | None = Field(default=None, min_length=1, max_length=512)
    strategy: str | None = Field(default=None, min_length=1, max_length=128)
    source_url: str | None = Field(default=None)

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


class ReindexAsyncResponse(BaseModel):
    job_id: str
    status: str = "pending"


class PushAsyncResponse(BaseModel):
    job_id: str
    status: str = "pending"


class DeleteAsyncResponse(BaseModel):
    job_id: str
    status: str = "pending"
