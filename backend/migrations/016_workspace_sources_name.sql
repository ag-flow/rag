-- Migration 016 — workspace_sources : ajout colonne name (clé fonctionnelle)
-- Nullable pour les sources existantes (créées avant cette migration).
-- L'unicité est garantie par un index partial (WHERE name IS NOT NULL) :
-- les lignes sans nom (legacy) ne participent pas à la contrainte.

ALTER TABLE workspace_sources ADD COLUMN name TEXT;

CREATE UNIQUE INDEX uq_workspace_sources_name
    ON workspace_sources (workspace_id, name)
    WHERE name IS NOT NULL;
