"""Garde « variable de gabarit non substituée » à l'ingestion (ticket 14a62570)."""

from __future__ import annotations

import pytest

from rag.api.errors import UnresolvedTemplateVariable
from rag.services.push import reject_unresolved_placeholders


def test_reject_path_with_dotted_placeholder_names_variable() -> None:
    with pytest.raises(UnresolvedTemplateVariable) as exc:
        reject_unresolved_placeholders(
            workspace="docflow", path="docflow/{event.blockSlug}/0111", title="Titre"
        )
    assert exc.value.to_payload() == {
        "error": "unresolved_template_variable",
        "field": "path",
        "variables": ["{event.blockSlug}"],
    }


def test_reject_title_with_placeholder_lists_every_variable() -> None:
    with pytest.raises(UnresolvedTemplateVariable) as exc:
        reject_unresolved_placeholders(
            workspace="a2a",
            path="a2a/documentation/33c7",
            title="[{event.functionalTypeSlug}] - {title}",
        )
    assert exc.value.field == "title"
    assert exc.value.variables == ["{event.functionalTypeSlug}", "{title}"]


@pytest.mark.parametrize(
    ("path", "title"),
    [
        ("docflow/documentation/0111", "[article] - Persistance & migrations"),
        ("docflow/documentation/0111", None),
        # Accolades qui ne sont pas un identifiant : JSON, ensembles, vides.
        ("src/{}.md", 'Format {"a": 1} et {1,2}'),
        ("docs/{a b}.md", "{ espace }"),
    ],
)
def test_accept_values_without_identifier_placeholder(path: str, title: str | None) -> None:
    reject_unresolved_placeholders(workspace="ws", path=path, title=title)
