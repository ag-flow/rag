-- Migration 033 — multi-clés API par workspace

CREATE TABLE workspace_api_keys (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    fingerprint  TEXT NOT NULL,
    api_key_ref  TEXT NOT NULL,
    revoked_at   TIMESTAMPTZ,
    rotated_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, fingerprint)
);

CREATE INDEX workspace_api_keys_ws ON workspace_api_keys (workspace_id);
CREATE INDEX workspace_api_keys_fp ON workspace_api_keys (fingerprint);

ALTER TABLE workspaces DROP COLUMN IF EXISTS api_key_fingerprint;
ALTER TABLE workspaces DROP COLUMN IF EXISTS api_key_ref;
