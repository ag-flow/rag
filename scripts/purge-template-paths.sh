#!/usr/bin/env bash
#
# purge-template-paths.sh — purge one-shot des documents indexés sous un chemin
# pollué `<ws>/{event.blockSlug}/<id>` (ticket backlog 14a62570).
#
# Usage, sur le host qui fait tourner la stack ragflow :
#   scripts/purge-template-paths.sh            # liste seulement, rien n'est modifié
#   scripts/purge-template-paths.sh --apply    # met en file un job 'delete' par document
#
# L'automate docflow a longtemps envoyé `{event.blockSlug}` littéral dans le
# path : ces documents ont un chemin inutilisable et un en-tête parasité. On ne
# les efface pas à la main dans les bases : on insère des jobs 'delete' exactement
# comme DELETE /api/v1/index, et c'est le worker qui retire chunks, embeddings et
# marqueur — même chemin de code, même trace dans l'historique des jobs. Aucune
# clé API n'est nécessaire : le script parle à la base de config du conteneur.
#
# Ne cible QUE les paths dont le 2e segment est exactement `{event.blockSlug}` :
# un document qui cite la variable dans son contenu n'est jamais touché.
# Rejouable : un path qui a déjà un job 'delete' en attente n'est pas ré-enfilé.
#
# PSQL_CMD surcharge la commande psql (tests) ; par défaut, psql du conteneur
# rag-postgres sur la base de config ($POSTGRES_DB, celle de DATABASE_URL).

set -euo pipefail

APPLY=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    *) echo "✗ Argument inconnu : ${arg} (seul --apply est accepté)" >&2; exit 1 ;;
  esac
done

if [ -z "${PSQL_CMD:-}" ]; then
  # Guillemets simples : $POSTGRES_USER / $POSTGRES_DB sont ceux du conteneur.
  PSQL_CMD=(docker exec -i rag-postgres sh -c 'psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"')
else
  read -r -a PSQL_CMD <<< "$PSQL_CMD"
fi

# Motif POSIX appliqué au path : <workspace>/{event.blockSlug}/<id>, rien d'autre.
TARGETS="
  SELECT d.workspace_id, w.name AS workspace, d.path
  FROM indexed_documents d
  JOIN workspaces w ON w.id = d.workspace_id
  WHERE d.path ~ '^[^/]+/\{event\.blockSlug\}/[^/]+\$'
    AND NOT EXISTS (
      SELECT 1 FROM index_jobs j
      WHERE j.workspace_id = d.workspace_id AND j.path = d.path
        AND j.triggered_by = 'delete' AND j.status IN ('pending', 'running')
    )"

if [ "$APPLY" = "0" ]; then
  "${PSQL_CMD[@]}" <<SQL
\pset footer on
SELECT workspace, path FROM (${TARGETS}) t ORDER BY workspace, path;
SELECT workspace, count(*) AS documents FROM (${TARGETS}) t GROUP BY workspace ORDER BY workspace;
SQL
  echo "Rien n'a été modifié. Relancer avec --apply pour mettre en file les suppressions."
  exit 0
fi

# Une seule transaction : soit tous les jobs et leurs payloads sont créés,
# soit aucun (pas de job 'delete' orphelin de payload que le worker rejetterait).
"${PSQL_CMD[@]}" <<SQL
BEGIN;
WITH targets AS (${TARGETS}),
jobs AS (
  INSERT INTO index_jobs (workspace_id, triggered_by, status, correlation_id, path)
  SELECT workspace_id, 'delete', 'pending', gen_random_uuid()::text, path FROM targets
  RETURNING id, workspace_id, path
),
payloads AS (
  INSERT INTO delete_job_payloads (job_id, path)
  SELECT id, path FROM jobs
  RETURNING job_id
)
SELECT w.name AS workspace, count(*) AS jobs_delete_enfiles
FROM jobs JOIN workspaces w ON w.id = jobs.workspace_id
WHERE jobs.id IN (SELECT job_id FROM payloads)
GROUP BY w.name ORDER BY w.name;
COMMIT;
SQL
echo "Jobs 'delete' mis en file : le worker les traite (suivi dans Push activity)."
