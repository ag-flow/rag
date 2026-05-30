-- Migration 019 — workspace_webhooks + webhook_headers

CREATE TABLE workspace_webhooks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    url           TEXT NOT NULL,
    enabled       BOOLEAN DEFAULT true,
    created_at    TIMESTAMPTZ DEFAULT now(),
    UNIQUE(workspace_id, name)
);

CREATE TABLE webhook_headers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_id  UUID NOT NULL REFERENCES workspace_webhooks(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    value       TEXT,
    vault_ref   TEXT,
    enabled     BOOLEAN DEFAULT true
);
