-- Migration 009 : coffres Harpocrate configurables côté DB (M5c)
-- Pré-requis : pgcrypto (activé en 001_init.sql)
-- Note : updated_at est maintenu côté service Python (pas de trigger), conformément
-- à la convention projet (cf. services/workspaces.py).

CREATE TABLE harpocrate_vaults (
    id                uuid PRIMARY KEY,
    name              text NOT NULL UNIQUE,
    label             text NOT NULL,
    base_url          text NOT NULL,
    api_key_id        text NOT NULL,
    api_key_encrypted bytea NOT NULL,
    probe_path        text NULL,
    is_default        boolean NOT NULL DEFAULT false,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX harpocrate_vaults_one_default
    ON harpocrate_vaults (is_default)
    WHERE is_default;

CREATE INDEX harpocrate_vaults_name ON harpocrate_vaults (name);
