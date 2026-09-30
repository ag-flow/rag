"""Erreurs PostgreSQL dont le code dépend de la version du serveur."""

from __future__ import annotations

import asyncpg

# Violation d'un `ON DELETE RESTRICT` : jusqu'à PostgreSQL 17 elle est signalée
# `foreign_key_violation` (23503) ; à partir de 18, `restrict_violation` (23001).
# La CI tourne en pg16, un poste ou une prod à jour en pg18 : accepter les deux,
# sinon le test ne dit plus rien du schéma mais seulement de la version.
RESTRICT_VIOLATION = (asyncpg.ForeignKeyViolationError, asyncpg.RestrictViolationError)
