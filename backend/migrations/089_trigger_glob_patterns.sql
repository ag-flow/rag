-- Migration 089 — triggers de workspace par pattern glob de chemin
--
-- Le déclenchement par extension (`.md`) devient un pattern glob sur le
-- chemin complet (`backlog/**/*.md`) : c'est le chemin qui porte la
-- sémantique du corpus quand un même workspace mélange plusieurs natures
-- de documents (décision architecte 2026-07-26, feature « MCP — binding
-- des stratégies »).
--
-- Backfill iso-comportement : chaque extension `.ext` devient `**/*.ext`
-- (matche l'extension à n'importe quelle profondeur, racine comprise).
-- Départage entre triggers concurrents : le pattern le plus spécifique
-- gagne — segments, puis longueur, puis ancienneté (voir rag/globmatch.py).
--
-- Le nom des tables `workspace_extension_triggers` /
-- `workspace_extension_trigger_prompts` est conservé (historique) : tout le
-- code les référence et le renommage n'apporterait rien fonctionnellement.

ALTER TABLE workspace_extension_triggers ADD COLUMN pattern TEXT;

UPDATE workspace_extension_triggers SET pattern = '**/*' || extension;

ALTER TABLE workspace_extension_triggers ALTER COLUMN pattern SET NOT NULL;

ALTER TABLE workspace_extension_triggers
    DROP CONSTRAINT workspace_extension_triggers_workspace_id_extension_key;

ALTER TABLE workspace_extension_triggers
    ADD CONSTRAINT workspace_extension_triggers_workspace_id_pattern_key
    UNIQUE (workspace_id, pattern);

ALTER TABLE workspace_extension_triggers DROP COLUMN extension;
