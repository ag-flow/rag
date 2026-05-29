-- Migration 024 — clés API provider stockées dans Harpocrate

CREATE TABLE provider_api_keys (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_id      TEXT NOT NULL,
    label       TEXT NOT NULL,
    provider    TEXT NOT NULL,
    vault_id    UUID NOT NULL REFERENCES harpocrate_vaults(id) ON DELETE RESTRICT,
    harpo_path  TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (vault_id, provider, key_id)
);
