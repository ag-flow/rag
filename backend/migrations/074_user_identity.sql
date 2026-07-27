-- Migration 074 — GUID d'identité OBO sur les utilisateurs (contrat OBO v6)
--
-- Le portail propage l'identité humaine via `x-portal-actor` = un GUID opaque
-- que l'utilisateur pose dans son profil portail ET ici (globals d0e2dad3,
-- GUID-only : jamais login/email, pas de repli sur le sub OIDC).
-- Le service mappe x-portal-actor sur l'utilisateur dont identity = cette
-- valeur. NULL = pas de propagation pour cet utilisateur (fail-safe).

ALTER TABLE users ADD COLUMN identity TEXT NULL;
ALTER TABLE users ADD CONSTRAINT users_identity_unique UNIQUE (identity);
