-- Migration 011 — rerank_configs : config rerank par workspace (opt-in)
--
-- Workspace SANS row dans cette table → pas de rerank (comportement par défaut).
-- Cascade ON DELETE : suppression workspace → suppression rerank_config auto.

CREATE TABLE rerank_configs (
    workspace_id        UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    provider            TEXT NOT NULL,
    model               TEXT NOT NULL,
    base_url            TEXT,
    api_key_ref         TEXT,
    top_k_pre_rerank    INT NOT NULL DEFAULT 50 CHECK (top_k_pre_rerank > 0),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
