-- Migration 001 — schémas de base : workspaces + indexer_configs
-- Conforme à specs/01-data-model.md + addition sync_interval_seconds (design 2026-05-14)

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE workspaces (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    TEXT NOT NULL UNIQUE,
    api_key_hash            TEXT NOT NULL,
    rag_cnx                 TEXT NOT NULL,
    rag_base                TEXT NOT NULL,
    sync_interval_seconds   INT NOT NULL DEFAULT 300,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_workspaces_name ON workspaces(name);

CREATE TABLE indexer_configs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    base_url        TEXT,
    api_key_ref     TEXT,
    dimension       INT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id)
);

CREATE INDEX idx_indexer_configs_workspace ON indexer_configs(workspace_id);
