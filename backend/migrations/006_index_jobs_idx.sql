-- Migration 006 — index sur index_jobs(workspace_id, started_at DESC NULLS LAST)
-- pour accélérer GET /workspaces/{name}/jobs (historique trié desc).
--
-- Complémentaire à idx_jobs_workspace_finished (migration 003) : ce dernier
-- est efficace pour les jobs terminés, mais NULL en pending/running. Trier
-- l'historique de l'API admin par started_at permet d'afficher les jobs en
-- cours en haut, suivis des terminés du plus récent au plus ancien.

CREATE INDEX IF NOT EXISTS idx_jobs_workspace_started
    ON index_jobs (workspace_id, started_at DESC NULLS LAST);
