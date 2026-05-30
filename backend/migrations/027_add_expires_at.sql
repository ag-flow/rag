-- Migration 027 — validité des clés API (expires_at)

ALTER TABLE provider_api_keys ADD COLUMN expires_at TIMESTAMPTZ NULL;
ALTER TABLE git_credentials    ADD COLUMN expires_at TIMESTAMPTZ NULL;
