from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

_PATH_MAX_LEN = 1024
_CONTENT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB UTF-8


class PushRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=_PATH_MAX_LEN)
    content: str = Field(..., min_length=1)
    title: str | None = Field(default=None, min_length=1, max_length=512)
    # Slug de stratégie (mode service, spec chunking §5) : résolu à l'acceptation
    # dans la bibliothèque du caller puis côté système. 128 = borne des labels
    # dont les slugs sont dérivés.
    strategy: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("content")
    @classmethod
    def _content_size(cls, v: str) -> str:
        if len(v.encode("utf-8")) > _CONTENT_MAX_BYTES:
            raise ValueError("content_too_large")
        return v


class ReindexRequest(BaseModel):
    """Ré-évaluation d'un document déjà poussé — le path vient de l'URL.

    L'appelant renvoie le contenu (aucun stockage source côté service) ; le
    re-traitement est forcé même si le contenu est identique, pour appliquer une
    stratégie de chunking ou un modèle d'embedding qui a changé depuis.
    """

    content: str = Field(..., min_length=1)
    title: str | None = Field(default=None, min_length=1, max_length=512)
    strategy: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("content")
    @classmethod
    def _content_size(cls, v: str) -> str:
        if len(v.encode("utf-8")) > _CONTENT_MAX_BYTES:
            raise ValueError("content_too_large")
        return v


class ReindexAsyncResponse(BaseModel):
    job_id: str
    status: str = "pending"


class PushAsyncResponse(BaseModel):
    job_id: str
    status: str = "pending"


class DeleteAsyncResponse(BaseModel):
    job_id: str
    status: str = "pending"
