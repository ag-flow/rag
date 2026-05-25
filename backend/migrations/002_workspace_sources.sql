-- Migration 002 — workspace_sources
-- Conforme à specs/01-data-model.md + addition next_sync_at (design 2026-05-14)

CREATE TABLE workspace_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    type            TEXT NOT NULL DEFAULT 'git',
    config          JSONB NOT NULL,
    last_indexed_at TIMESTAMPTZ,
    next_sync_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_workspace_sources_workspace ON workspace_sources(workspace_id);
CREATE INDEX idx_sources_next_sync ON workspace_sources(next_sync_at)
    WHERE next_sync_at IS NOT NULL;
