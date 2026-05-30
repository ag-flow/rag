-- Migration 030 — configs LLM par workspace (RAG Playground)

CREATE TABLE workspace_llm_configs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    provider     TEXT NOT NULL,
    model        TEXT NOT NULL,
    base_url     TEXT,
    api_key_ref  TEXT,
    enabled      BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (workspace_id, provider, model)
);

CREATE INDEX workspace_llm_configs_ws ON workspace_llm_configs (workspace_id);
