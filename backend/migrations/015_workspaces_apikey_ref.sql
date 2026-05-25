-- Migration 015 — workspaces : api_key_encrypted → api_key_ref (Harpocrate)
-- Greenfield : la DB est recréée from scratch (workspaces table vide).
-- Cf. spec docs/superpowers/specs/2026-05-21-consolidate-workspace-apikeys-design.md.
--
-- ALTER TABLE NOT NULL sans DEFAULT : si la table contient des rows, la
-- migration échoue. C'est intentionnel — l'opérateur doit DROP la DB et
-- recréer (pas de migration partielle silencieuse).

ALTER TABLE workspaces
    DROP COLUMN api_key_encrypted,
    ADD COLUMN api_key_ref TEXT NOT NULL;

-- api_key_fingerprint (TEXT) conservé : lookup O(1) bearer auth via index.
