"""Contrat OpenAPI 3.1 des events émis par ragflow (à importer côté workflow).

Section racine `webhooks` (Option 1 du guide producteur) : une clé par event,
`operationId` = nom sans provider (workflow le préfixe), `requestBody.schema` =
data_schema métier. Ne décrit PAS les champs `_…` de l'enveloppe.
"""

from __future__ import annotations

from typing import Any

from rag.events.registry import EVENT_SPECS


def build_events_contract() -> dict[str, Any]:
    webhooks: dict[str, Any] = {}
    for spec in EVENT_SPECS:
        # Clé webhook = operationId sans le suffixe .vN (nom logique de l'event).
        op_id = spec.operation_id()
        key = op_id.rsplit(".v", 1)[0] if ".v" in op_id else op_id
        webhooks[key] = {
            "post": {
                "operationId": op_id,
                "summary": spec.summary,
                "requestBody": {
                    "content": {"application/json": {"schema": spec.data_schema}}
                },
            }
        }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Events ragflow",
            "version": "1.0.0",
            "description": (
                "Événements émis par ragflow vers ag.flow workflow (Porte A). "
                "À importer sur la source inbound côté workflow."
            ),
        },
        "webhooks": webhooks,
    }
