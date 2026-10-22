from __future__ import annotations

import logging
import sys
from typing import Literal

import structlog

Environment = Literal["dev", "staging", "prod"]

# Routes dont la query string porte un secret à usage unique : le retour de
# « Connecter à Harpocrate » reçoit `code` et `state` (contrat Harpocrate :
# ni l'un ni l'autre ne se journalisent). uvicorn écrit l'URL complète dans
# son journal d'accès — on n'y garde que le chemin.
_REDACTED_QUERY_PATHS = ("/api/admin/harpocrate-vaults/connect/callback",)


class _RedactSensitiveQueryFilter(logging.Filter):
    """Retire la query string des lignes d'accès uvicorn des routes sensibles."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        # Format uvicorn.access : (client, méthode, chemin complet, version, statut).
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            path, _, query = args[2].partition("?")
            if query and path in _REDACTED_QUERY_PATHS:
                record.args = (*args[:2], f"{path}?<masqué>", *args[3:])
        return True


def setup_logging(level: str, environment: Environment) -> None:
    """Configure structlog + stdlib logging.

    - `dev`        → console renderer sans couleurs (lisible humain, testable avec capsys).
    - `staging`/`prod` → JSONRenderer (consommable par Alloy/Loki en M6).
    """
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {level!r}")

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
        force=True,
    )
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _RedactSensitiveQueryFilter) for f in access_logger.filters):
        access_logger.addFilter(_RedactSensitiveQueryFilter())

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor
    if environment == "dev":
        renderer = structlog.dev.ConsoleRenderer(colors=False)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
