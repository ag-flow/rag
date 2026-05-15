-- Migration 006 — index sur index_jobs(workspace_id, started_at DESC NULLS LAST)
-- pour accélérer GET /workspaces/{name}/jobs (historique trié desc).

CREATE INDEX IF NOT EXISTS index_jobs_workspace_started
    ON index_jobs (workspace_id, started_at DESC NULLS LAST);
