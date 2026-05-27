-- Migration 012 — chunking_configs : config chunking par workspace (obligatoire)
--
-- 1 row par workspace. La row est créée à la création du workspace.
-- Migration peuple les workspaces existants avec la stratégie 'paragraph' + valeurs actuelles.
-- Cascade ON DELETE : suppression workspace → suppression chunking_config auto.

CREATE TABLE chunking_configs (
    workspace_id    UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    strategy        TEXT NOT NULL CHECK (strategy IN ('paragraph')),
    max_chars       INT  NOT NULL CHECK (max_chars  > 0),
    min_chars       INT  NOT NULL CHECK (min_chars  >= 0 AND min_chars < max_chars),
    overlap_chars   INT  NOT NULL CHECK (overlap_chars >= 0 AND overlap_chars < max_chars),
    extras          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO chunking_configs (workspace_id, strategy, max_chars, min_chars, overlap_chars)
SELECT id, 'paragraph', 2000, 200, 200
FROM workspaces
ON CONFLICT (workspace_id) DO NOTHING;
