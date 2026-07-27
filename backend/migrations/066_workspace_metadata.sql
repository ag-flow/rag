-- Migration 066 — métadonnées d'affichage du workspace : label + description
--
-- `name` reste l'IDENTIFIANT/slug du workspace : unique, normalisé
-- (regex ^[a-z][a-z0-9_-]{0,62}$), sert au nom de la base physique (rag_<name>)
-- et à toutes les URLs. Il n'est PAS modifié par cette migration.
--
-- Ajout purement additif de deux métadonnées libres :
--   - label       : nom d'affichage lisible (le front en dérive le slug `name`)
--   - description : texte libre décrivant le workspace
--
-- Backfill : pour les workspaces existants, label = name (affichage neutre,
-- l'admin pourra le personnaliser ensuite).

ALTER TABLE workspaces
    ADD COLUMN label TEXT,
    ADD COLUMN description TEXT NOT NULL DEFAULT '';

UPDATE workspaces SET label = name WHERE label IS NULL;
