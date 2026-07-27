-- Migration 058 — possession des templates d'enrichissement (spec chunking §4, F3)
--
-- Même modèle que chunking_strategies (057) : owner_id NULL = template
-- SYSTÈME (visible de tous, non éditable, non supprimable), sinon
-- sha256(email) du propriétaire. Les templates existants (créés avant la
-- possession) deviennent système. Les triggers continuent de référencer les
-- templates PAR ID — aucun changement de comportement d'indexation.

ALTER TABLE prompt_templates ADD COLUMN owner_id TEXT;

-- Unicité du nom par bibliothèque (système / par owner) au lieu de globale.
ALTER TABLE prompt_templates DROP CONSTRAINT prompt_templates_name_key;
CREATE UNIQUE INDEX prompt_templates_system_name
    ON prompt_templates (name) WHERE owner_id IS NULL;
CREATE UNIQUE INDEX prompt_templates_owner_name
    ON prompt_templates (owner_id, name) WHERE owner_id IS NOT NULL;

-- Unicité de la clé de métadonnée par bibliothèque ET par langue : deux
-- templates d'une même langue ne peuvent pas écrire la même clé (la clé reste
-- volontairement partageable entre langues — ex. « documentation » pour
-- python et csharp — c'est le modèle multi-langue de la migration 031).
CREATE UNIQUE INDEX prompt_templates_system_metadata_key
    ON prompt_templates (language, metadata_key) WHERE owner_id IS NULL;
CREATE UNIQUE INDEX prompt_templates_owner_metadata_key
    ON prompt_templates (owner_id, language, metadata_key) WHERE owner_id IS NOT NULL;
