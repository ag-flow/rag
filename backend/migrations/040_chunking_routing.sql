-- Migration 040 — routage du chunking structure-aware (ADR 0001 §2)
--
-- Trois objets de config, chacun avec un défaut GLOBAL (workspace_id NULL) et
-- une surcharge optionnelle par workspace :
--   1. chunking_strategies         : catalogue nommé (algo + params).
--   2. chunking_extension_categories : extension -> catégorie.
--   3. chunking_category_strategies  : catégorie -> nom de stratégie.
--
-- + flag par workspace `chunking_configs.engine` (legacy|structured). Défaut
--   'legacy' : aucun changement de comportement tant qu'on ne bascule pas. Les
--   workspaces existants restent sur l'ancien pipeline (chunking_configs), donc
--   AUCUNE migration de leurs données n'est nécessaire ici.
--
-- L'unicité distingue global (workspace_id IS NULL) et par-workspace via deux
-- index partiels (NULL non dédupliqué par un UNIQUE classique en Postgres).

-- 1. Flag de bascule par workspace -------------------------------------------
ALTER TABLE chunking_configs
    ADD COLUMN engine TEXT NOT NULL DEFAULT 'legacy'
        CHECK (engine IN ('legacy', 'structured'));

-- 2. Catalogue de stratégies nommées -----------------------------------------
CREATE TABLE chunking_strategies (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,  -- NULL = global
    name         TEXT NOT NULL,
    algo         TEXT NOT NULL CHECK (algo IN ('prose', 'markdown', 'table', 'code')),
    params       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX chunking_strategies_global_name
    ON chunking_strategies (name) WHERE workspace_id IS NULL;
CREATE UNIQUE INDEX chunking_strategies_ws_name
    ON chunking_strategies (workspace_id, name) WHERE workspace_id IS NOT NULL;

-- 3. Extension -> catégorie ---------------------------------------------------
CREATE TABLE chunking_extension_categories (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,  -- NULL = global
    extension    TEXT NOT NULL,   -- forme '.md' (minuscule, point initial)
    category     TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX chunking_ext_cat_global
    ON chunking_extension_categories (extension) WHERE workspace_id IS NULL;
CREATE UNIQUE INDEX chunking_ext_cat_ws
    ON chunking_extension_categories (workspace_id, extension) WHERE workspace_id IS NOT NULL;

-- 4. Catégorie -> stratégie ---------------------------------------------------
CREATE TABLE chunking_category_strategies (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID REFERENCES workspaces(id) ON DELETE CASCADE,  -- NULL = global
    category      TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX chunking_cat_strat_global
    ON chunking_category_strategies (category) WHERE workspace_id IS NULL;
CREATE UNIQUE INDEX chunking_cat_strat_ws
    ON chunking_category_strategies (workspace_id, category) WHERE workspace_id IS NOT NULL;

-- 5. Seeds GLOBAUX ------------------------------------------------------------
-- NB : 'code-aware' a l'algo 'prose' en Lot 1 (code routé vers prose, borné en
-- tokens). Lot 2 basculera son algo vers 'code' (tree-sitter) par un UPDATE.
INSERT INTO chunking_strategies (workspace_id, name, algo, params) VALUES
    (NULL, 'markdown-deep', 'prose',
     '{"child_target_tokens":384,"floor_tokens":64,"overlap_tokens":64,"breadcrumb_depth":-1,"heading_levels":[1,2]}'::jsonb),
    (NULL, 'code-aware', 'prose',
     '{"child_target_tokens":512,"floor_tokens":64,"overlap_tokens":64,"breadcrumb_depth":-1,"heading_levels":[1,2,3]}'::jsonb),
    (NULL, 'table', 'table',
     '{"child_target_tokens":512,"max_rows_per_chunk":50}'::jsonb);

INSERT INTO chunking_category_strategies (workspace_id, category, strategy_name) VALUES
    (NULL, 'prose', 'markdown-deep'),
    (NULL, 'code',  'code-aware'),
    (NULL, 'table', 'table'),
    (NULL, 'data',  'code-aware');

INSERT INTO chunking_extension_categories (workspace_id, extension, category) VALUES
    (NULL, '.md', 'prose'), (NULL, '.markdown', 'prose'), (NULL, '.txt', 'prose'),
    (NULL, '.rst', 'prose'),
    (NULL, '.py', 'code'), (NULL, '.ts', 'code'), (NULL, '.tsx', 'code'),
    (NULL, '.js', 'code'), (NULL, '.jsx', 'code'), (NULL, '.go', 'code'),
    (NULL, '.rs', 'code'), (NULL, '.java', 'code'), (NULL, '.c', 'code'),
    (NULL, '.h', 'code'), (NULL, '.cpp', 'code'), (NULL, '.hpp', 'code'),
    (NULL, '.sql', 'code'), (NULL, '.sh', 'code'), (NULL, '.rb', 'code'),
    (NULL, '.php', 'code'), (NULL, '.css', 'code'), (NULL, '.scss', 'code'),
    (NULL, '.csv', 'table'), (NULL, '.tsv', 'table'),
    (NULL, '.json', 'data'), (NULL, '.yaml', 'data'), (NULL, '.yml', 'data'),
    (NULL, '.toml', 'data'), (NULL, '.xml', 'data'), (NULL, '.ini', 'data');
