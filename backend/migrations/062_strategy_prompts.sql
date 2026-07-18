-- Migration 062 — prompts d'enrichissement liés PAR STRATÉGIE (F6, S6.4)
--
-- Deuxième chemin d'activation du contexte inline (le premier : les triggers
-- par extension, workspace-scopés). Un binding stratégie voyage AVEC la
-- stratégie dans tous les workspaces qui l'utilisent — le template porte la
-- sémantique ; le LLM d'exécution est résolu au runtime dans le workspace
-- (première config LLM active), car workspace_llm_configs est par workspace
-- alors que les stratégies sont user/système (écart assumé avec le texte de
-- S6.4 qui mettait le LLM dans le binding — posé en review).
--
-- ON DELETE RESTRICT côté template : un template lié à une stratégie n'est
-- pas supprimable (compteur « utilisé par N » côté IHM).

CREATE TABLE chunking_strategy_prompts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id UUID NOT NULL REFERENCES chunking_strategies(id) ON DELETE CASCADE,
    template_id UUID NOT NULL REFERENCES prompt_templates(id) ON DELETE RESTRICT,
    order_index INT  NOT NULL DEFAULT 1,
    enabled     BOOL NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (strategy_id, template_id)
);

CREATE INDEX chunking_strategy_prompts_strategy
    ON chunking_strategy_prompts (strategy_id, order_index);
