-- Migration 017 — fichiers traités par job (détail "ce qui a été fait")
CREATE TABLE index_job_files (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id      UUID NOT NULL REFERENCES index_jobs(id) ON DELETE CASCADE,
    path        TEXT NOT NULL,
    change_type TEXT NOT NULL CHECK (change_type IN ('added', 'modified', 'deleted'))
);

CREATE INDEX idx_job_files_job ON index_job_files(job_id);
