from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rag.schemas.admin import _NAME_REGEX


class WorkspaceApikeyCreateRequest(BaseModel):
    """Corps de POST /api/v1/workspaces — mêmes paramètres que l'outil MCP
    `create_workspace` : l'endpoint est désigné par coffre + slug, lisibles."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        pattern=_NAME_REGEX,
        max_length=63,
        description="Slug du workspace : minuscule en tête, puis minuscules, chiffres, _ ou -.",
    )
    label: str | None = Field(
        default=None, min_length=1, max_length=128, description="Libellé (défaut : name)."
    )
    description: str = Field(default="", max_length=2000)
    vault: str = Field(
        min_length=1,
        max_length=64,
        description="Coffre Harpocrate portant l'endpoint (coffre par défaut ou possédé).",
    )
    endpoint: str = Field(
        min_length=1,
        max_length=128,
        description="Slug de l'endpoint dont la configuration est copiée (snapshot).",
    )


class WorkspaceApikeyDeleteRequest(BaseModel):
    """Corps de DELETE /api/v1/workspaces. `confirm` doit valoir `true` : la
    suppression détruit la base pgvector du workspace, sans retour possible."""

    model_config = ConfigDict(extra="forbid")

    workspace: str = Field(pattern=_NAME_REGEX, max_length=63)
    confirm: Literal[True] = Field(
        description="Doit valoir true — garde-fou contre une suppression irréversible."
    )
