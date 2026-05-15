-- Migration 007 — étend la CHECK constraint sur index_jobs.triggered_by
-- pour accepter 'reindex_indexer_change', utilisée lors d'un changement
-- d'indexeur (drop+recreate de la table embeddings, cf. services/jobs.reindex_workspace
-- et design 2026-05-15-M2-api-admin-design.md, Flow C).

ALTER TABLE index_jobs DROP CONSTRAINT index_jobs_triggered_by_check;

ALTER TABLE index_jobs ADD CONSTRAINT index_jobs_triggered_by_check
    CHECK (triggered_by IN ('webhook', 'manual', 'push', 'schedule', 'reindex_indexer_change'));
