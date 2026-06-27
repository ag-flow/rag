-- Migration 044 — endpoint DELETE /workspaces/{name}/index/{path}
--
-- Ajoute le triggered_by 'delete' et la table de payload associée.

ALTER TABLE index_jobs DROP CONSTRAINT index_jobs_triggered_by_check;

ALTER TABLE index_jobs ADD CONSTRAINT index_jobs_triggered_by_check
    CHECK (triggered_by IN (
        'webhook',
        'manual',
        'push',
        'delete',
        'schedule',
        'reindex_indexer_change',
        'reindex_chunking_change'
    ));

CREATE TABLE delete_job_payloads (
    job_id  UUID PRIMARY KEY REFERENCES index_jobs(id) ON DELETE CASCADE,
    path    TEXT NOT NULL
);
