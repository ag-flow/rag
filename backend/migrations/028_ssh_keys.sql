-- Migration 028 — clés SSH dans les coffres Harpocrate

CREATE TABLE ssh_keys (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_id               TEXT NOT NULL,
    name                 TEXT NOT NULL,
    key_type             TEXT NOT NULL,
    public_key           TEXT NOT NULL,
    passphrase_protected BOOLEAN NOT NULL DEFAULT false,
    vault_id             UUID NOT NULL REFERENCES harpocrate_vaults(id) ON DELETE RESTRICT,
    harpo_path           TEXT NOT NULL,
    created_at           TIMESTAMPTZ DEFAULT now(),
    UNIQUE (vault_id, key_id)
);
