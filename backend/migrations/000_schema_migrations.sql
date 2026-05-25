-- Table de suivi des migrations appliquées.
-- Doit exister avant que le runner essaie d'appliquer la première migration métier.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
