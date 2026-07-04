-- Migration 049 — flag confidentialité par workspace pour get_document
--
-- allow_full_read=TRUE (défaut) → comportement inchangé pour tous les workspaces existants.
-- Mettre à FALSE pour un workspace sensible : get_document refusé, search_files autorisé.

ALTER TABLE workspaces
    ADD COLUMN allow_full_read BOOLEAN NOT NULL DEFAULT TRUE;
