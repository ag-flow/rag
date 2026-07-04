-- Migration 052 — created_at sur index_jobs pour un ordonnancement FIFO fiable
-- BUG-037 : le picker triait sur `id` (UUID v4 aléatoire), l'ordre n'était donc
-- pas chronologique et un job ancien pouvait être bypassé indéfiniment. On ajoute
-- un `created_at` (DEFAULT now(), rempli pour les lignes existantes) et on l'indexe
-- pour le picker « job pending le plus ancien ».

ALTER TABLE index_jobs
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_jobs_pending_created_at
    ON index_jobs (created_at)
    WHERE status = 'pending';
