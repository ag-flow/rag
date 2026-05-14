-- Migration 004 — oidc_config (table créée en M1, peuplée en M5)
-- Conforme à specs/10-auth.md

CREATE TABLE oidc_config (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issuer              TEXT NOT NULL,
    client_id           TEXT NOT NULL,
    client_secret_ref   TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
