-- Migration 060 — bindings de stratégie PAR ID : défaut workspace + triggers
-- (spec chunking §5 mode job, suite S5.1 — chantier « binding par id »)
--
-- Deux liens durables, consommés par le worker sans aucun contexte user :
--   1. `chunking_configs.default_strategy_id` : stratégie par défaut du
--      workspace (moteur structured). Prend le pas sur la résolution textuelle
--      de la catégorie par défaut ('prose') — les catégories spécialisées
--      (code/table/data) gardent la cascade existante.
--   2. `workspace_extension_triggers.strategy_id` : stratégie de chunking des
--      fichiers de cette extension dans ce workspace. Priorité : binding
--      explicite du push > trigger > cascade extension > défaut workspace.
--
-- ON DELETE RESTRICT (contrairement au payload transient de 059) : ces
-- bindings sont durables — une stratégie référencée n'est pas supprimable,
-- le compteur « utilisée par N » l'expose côté IHM.

ALTER TABLE chunking_configs
    ADD COLUMN default_strategy_id UUID REFERENCES chunking_strategies(id) ON DELETE RESTRICT;

ALTER TABLE workspace_extension_triggers
    ADD COLUMN strategy_id UUID REFERENCES chunking_strategies(id) ON DELETE RESTRICT;
