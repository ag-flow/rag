-- Migration 046 — retry avec backoff + circuit breaker par workspace

-- Colonnes retry sur index_jobs
ALTER TABLE index_jobs ADD COLUMN retry_count  INT NOT NULL DEFAULT 0;
ALTER TABLE index_jobs ADD COLUMN retry_after  TIMESTAMPTZ;

-- Circuit breaker : 1 entrée = circuit ouvert pour ce workspace
-- Absence de ligne = circuit fermé
CREATE TABLE indexer_circuit_breakers (
    workspace_id    UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    opened_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    open_until      TIMESTAMPTZ,          -- NULL = fermeture manuelle uniquement
    error_message   TEXT
);
