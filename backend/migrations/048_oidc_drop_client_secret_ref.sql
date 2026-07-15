-- Migration 048 — retire oidc_config.client_secret_ref
--
-- Le client secret OIDC est désormais lu depuis le .env
-- (RAG_OIDC_CLIENT_SECRET), source de vérité unique. Plus de référence
-- Harpocrate en base : la table ne stocke que issuer + client_id.

ALTER TABLE oidc_config DROP COLUMN client_secret_ref;
