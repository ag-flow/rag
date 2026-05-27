-- Migration 010 — workspaces.api_key : bcrypt → pgcrypto (chiffrement réversible)
--
-- Préconditions :
--   - Extension pgcrypto déjà activée (migration 009).
--   - Table workspaces vide (vérifié à blanc sur BDD test au design M5e).
--
-- Note : la rotation de RAG_API_KEY_DEK est hors-scope. Une perte de DEK
-- rend toutes les api_keys workspace inutilisables (réindexation requise).

ALTER TABLE workspaces DROP COLUMN api_key_hash;

ALTER TABLE workspaces
    ADD COLUMN api_key_encrypted BYTEA NOT NULL,
    ADD COLUMN api_key_fingerprint TEXT NOT NULL;

CREATE UNIQUE INDEX idx_workspaces_apikey_fingerprint
    ON workspaces (api_key_fingerprint);
