-- Migration 078 — le registre des modèles accueille les LLM (kind)
--
-- La table des modèles (page Models) devient le référentiel UNIQUE des modèles
-- proposés dans les endpoints : embedding (avec dimension) ET llm (sans
-- dimension — un LLM ne vectorise pas). L'onglet LLM d'un endpoint liste les
-- modèles kind='llm' du provider choisi.

ALTER TABLE model_dimensions
    ADD COLUMN kind TEXT NOT NULL DEFAULT 'embedding'
    CHECK (kind IN ('embedding', 'llm'));

ALTER TABLE model_dimensions ALTER COLUMN dimension DROP NOT NULL;
ALTER TABLE model_dimensions DROP CONSTRAINT model_dimensions_dimension_check;
ALTER TABLE model_dimensions ADD CONSTRAINT model_dimensions_dimension_check
    CHECK (
        (kind = 'embedding' AND dimension IS NOT NULL AND dimension > 0)
        OR (kind = 'llm' AND dimension IS NULL)
    );
