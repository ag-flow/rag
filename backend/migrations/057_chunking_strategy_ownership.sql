-- Migration 057 — possession des stratégies de chunking (spec chunking §4, F3)
--
-- Une stratégie devient un objet nommé et possédé :
--   - owner_id NULL = stratégie SYSTÈME (visible de tous, non éditable, non
--     supprimable) ; sinon sha256(email) du propriétaire — même convention que
--     user_api_keys / harpocrate_vaults (les utilisateurs OIDC n'ont pas de
--     ligne dans `users`, une FK UUID serait inapplicable) ;
--   - `label` saisi librement, `slug` DÉRIVÉ du label côté serveur (jamais
--     saisi ni éditable) ;
--   - `parser_slug` optionnel : active la passe régions (RoutingChunker).
--
-- `name` disparaît au profit de `slug` : les seeds étant déjà en forme slug
-- (markdown-deep, code-aware, table, data-structured), les références
-- textuelles `chunking_category_strategies.strategy_name` restent valides.

ALTER TABLE chunking_strategies
    ADD COLUMN owner_id    TEXT,
    ADD COLUMN label       TEXT,
    ADD COLUMN slug        TEXT,
    ADD COLUMN parser_slug TEXT REFERENCES chunking_parsers(slug);

UPDATE chunking_strategies SET label = name, slug = name;

ALTER TABLE chunking_strategies
    ALTER COLUMN label SET NOT NULL,
    ALTER COLUMN slug  SET NOT NULL;

DROP INDEX chunking_strategies_global_name;
DROP INDEX chunking_strategies_ws_name;
ALTER TABLE chunking_strategies DROP COLUMN name;

-- Unicité par portée : système, bibliothèque utilisateur, override workspace.
CREATE UNIQUE INDEX chunking_strategies_system_slug
    ON chunking_strategies (slug) WHERE owner_id IS NULL AND workspace_id IS NULL;
CREATE UNIQUE INDEX chunking_strategies_owner_slug
    ON chunking_strategies (owner_id, slug) WHERE owner_id IS NOT NULL;
CREATE UNIQUE INDEX chunking_strategies_ws_slug
    ON chunking_strategies (workspace_id, slug) WHERE workspace_id IS NOT NULL;

-- Une stratégie appartient à un user OU surcharge un workspace, jamais les deux.
ALTER TABLE chunking_strategies
    ADD CONSTRAINT chunking_strategies_owner_xor_ws
        CHECK (owner_id IS NULL OR workspace_id IS NULL);
