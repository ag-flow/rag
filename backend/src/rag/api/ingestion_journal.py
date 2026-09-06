from __future__ import annotations

import json
from typing import Any

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = structlog.get_logger(__name__)

_JOURNALED_METHODS = frozenset({"POST", "DELETE"})
_JOURNALED_PATH = "/api/v1/index"
_RETENTION_DAYS = 7

_AUTH_REASONS = {
    # Legacy (chemin require_workspace_apikey) — conservé pour l'historique.
    "invalid_workspace_apikey": "Workspace inconnu ou non autorisé pour cette clé",
    "invalid_apikey": "Clé API invalide",
    "insufficient_scope": "Niveau de la clé insuffisant (écriture requise)",
    "missing_bearer_token": "En-tête Authorization manquant",
    "invalid_auth_scheme": "Schéma d'authentification invalide (attendu : Bearer)",
}


def _validation_fields(detail: Any) -> str:
    """Résume les champs fautifs d'une erreur de validation 422 (loc[-1])."""
    if not isinstance(detail, list):
        return ""
    names: list[str] = []
    for err in detail:
        loc = err.get("loc") if isinstance(err, dict) else None
        if loc:
            names.append(str(loc[-1]))
    return ", ".join(dict.fromkeys(names))


def rejection_reason(http_status: int, detail: Any) -> str:
    """Traduit (code HTTP, detail interne) en motif clair et lisible."""
    if http_status == 401:
        if isinstance(detail, str) and detail in _AUTH_REASONS:
            return _AUTH_REASONS[detail]
        return "Non authentifié"
    if http_status == 422:
        fields = _validation_fields(detail)
        return f"Corps invalide : {fields}" if fields else "Corps de requête invalide"
    if http_status == 413:
        return "Contenu trop volumineux"
    if http_status == 404:
        if detail == "workspace_not_found":
            return "Workspace inconnu (à créer avant de pousser)"
        return "Ressource introuvable"
    if isinstance(detail, str) and detail:
        return detail
    return f"Rejeté (HTTP {http_status})"


class IngestionJournalMiddleware:
    """Journalise les demandes d'ingestion REJETÉES (POST/DELETE /api/v1/index).

    Les demandes acceptées (202) apparaissent déjà comme index_jobs ; ici on
    capture UNIFORMÉMENT tout rejet (401 clé/workspace, 422 corps, 404…), quelle
    que soit la couche qui le lève, en observant le code de réponse. Middleware
    ASGI pur : bufferise le corps entrant (workspace/path), rejoue-le au handler,
    et capture le statut + le detail de la réponse pour en déduire un motif clair.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") not in _JOURNALED_METHODS
            or scope.get("path") != _JOURNALED_PATH
        ):
            await self.app(scope, receive, send)
            return

        req_body = await _drain_body(receive)
        status = 200
        resp_body = b""

        async def replay() -> Message:
            return {"type": "http.request", "body": req_body, "more_body": False}

        async def capture(message: Message) -> None:
            nonlocal status, resp_body
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body":
                resp_body += message.get("body", b"")
            await send(message)

        await self.app(scope, replay, capture)

        if status >= 400:
            await self._record(scope, req_body, status, resp_body)

    async def _record(self, scope: Scope, req_body: bytes, status: int, resp_body: bytes) -> None:
        try:
            pool = scope["app"].state.pools.config_pool
        except Exception:  # pool non prêt (hors requête normale) — on n'ébruite pas
            return

        workspace = _json_str(req_body, "workspace")
        doc_path = _json_str(req_body, "path")
        detail = None
        try:
            detail = json.loads(resp_body).get("detail")
        except Exception:
            detail = None
        reason = rejection_reason(status, detail)

        try:
            await pool.execute(
                "INSERT INTO ingestion_rejections "
                "(method, workspace, doc_path, http_status, reason) "
                "VALUES ($1, $2, $3, $4, $5)",
                scope.get("method"),
                workspace,
                doc_path,
                status,
                reason,
            )
            # Purge opportuniste (les rejets sont rares) : rétention 7 jours.
            await pool.execute(
                "DELETE FROM ingestion_rejections "
                "WHERE received_at < now() - make_interval(days => $1)",
                _RETENTION_DAYS,
            )
        except Exception as exc:  # journalisation best-effort — jamais bloquant
            log.warning("ingestion_journal.record_failed", error=str(exc))


async def _drain_body(receive: Receive) -> bytes:
    """Lit tout le corps de la requête (http.request messages)."""
    body = b""
    while True:
        message = await receive()
        if message["type"] != "http.request":
            break
        body += message.get("body", b"")
        if not message.get("more_body", False):
            break
    return body


def _json_str(raw: bytes, key: str) -> str | None:
    """Extrait une valeur str d'un corps JSON (None si absent/illisible/non-str)."""
    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        return None
    value = data.get(key) if isinstance(data, dict) else None
    return value if isinstance(value, str) else None
