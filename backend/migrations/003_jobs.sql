-- Migration 003 — index_jobs + indexed_documents
-- Conforme à specs/01-data-model.md + specs/07-deduplication.md

CREATE TABLE index_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_id       UUID REFERENCES workspace_sources(id) ON DELETE SET NULL,
    triggered_by    TEXT NOT NULL CHECK (triggered_by IN ('webhook', 'manual', 'push', 'schedule')),
    status          TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'running', 'done', 'error')),
    files_changed   INT NOT NULL DEFAULT 0,
    files_skipped   INT NOT NULL DEFAULT 0,
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    duration_ms     INT
);

CREATE INDEX idx_jobs_status_workspace ON index_jobs(status, workspace_id);
CREATE INDEX idx_jobs_workspace_finished ON index_jobs(workspace_id, finished_at DESC NULLS LAST);

CREATE TABLE indexed_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    path            TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    indexer_used    TEXT NOT NULL,
    indexed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, path)
);

CREATE INDEX idx_docs_workspace ON indexed_documents(workspace_id);
