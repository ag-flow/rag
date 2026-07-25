-- Migration 073 — journal des demandes d'ingestion REJETÉES
--
-- Les demandes ACCEPTÉES (202) apparaissent déjà comme index_jobs. Les rejets
-- (401 workspace/clé, 422 corps invalide, 404…) ne créent aucun job → aucune
-- trace. On les journalise ici pour les afficher dans Push activity (union),
-- avec un motif clair. Rétention courte (purge > 7 jours, cf. middleware).

CREATE TABLE ingestion_rejections (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    received_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    method         TEXT NOT NULL,              -- POST | DELETE
    workspace      TEXT,                        -- slug demandé (peut être inconnu)
    doc_path       TEXT,                        -- path demandé si lisible
    http_status    INT NOT NULL,
    reason         TEXT NOT NULL,               -- motif clair (mappé du code interne)
    correlation_id TEXT
);

CREATE INDEX idx_ingestion_rejections_received ON ingestion_rejections (received_at DESC);
