-- Migration 025 — tokens Git stockés dans Harpocrate

CREATE TABLE git_credentials (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_id     TEXT NOT NULL,
    label      TEXT NOT NULL,
    host       TEXT NOT NULL,
    scope_url  TEXT NULL,
    vault_id   UUID NOT NULL REFERENCES harpocrate_vaults(id) ON DELETE RESTRICT,
    harpo_path TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (vault_id, host, key_id)
);
