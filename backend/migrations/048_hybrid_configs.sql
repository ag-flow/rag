-- Migration 048 — hybrid_configs : config recherche hybride par workspace (opt-in)
--
-- Workspace SANS row dans cette table → recherche vectorielle pure (comportement par défaut).
-- Cascade ON DELETE : suppression workspace → suppression hybrid_config auto.

CREATE TABLE hybrid_configs (
    workspace_id  UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    rrf_k         INT NOT NULL DEFAULT 60 CHECK (rrf_k > 0),
    fts_config    TEXT NOT NULL DEFAULT 'simple',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
