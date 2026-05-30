-- Migration 018 — push async : correlation_id + status skipped + push_job_payloads

ALTER TABLE index_jobs DROP CONSTRAINT index_jobs_status_check;
ALTER TABLE index_jobs ADD CONSTRAINT index_jobs_status_check
    CHECK (status IN ('pending', 'running', 'done', 'error', 'skipped'));

ALTER TABLE index_jobs ADD COLUMN correlation_id TEXT;

CREATE TABLE push_job_payloads (
    job_id   UUID PRIMARY KEY REFERENCES index_jobs(id) ON DELETE CASCADE,
    path     TEXT NOT NULL,
    content  TEXT NOT NULL
);
