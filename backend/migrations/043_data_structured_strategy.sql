-- Migration 043 — Lot 2c : catégorie 'data' (JSON/YAML/TOML) → algo structuré
-- dédié 'data' (découpe par clé de premier niveau via tree-sitter), au lieu de
-- réutiliser 'code-aware'. Fallback prose si le format n'est pas supporté.

ALTER TABLE chunking_strategies DROP CONSTRAINT chunking_strategies_algo_check;
ALTER TABLE chunking_strategies ADD CONSTRAINT chunking_strategies_algo_check
    CHECK (algo IN ('prose', 'markdown', 'table', 'code', 'data'));

INSERT INTO chunking_strategies (workspace_id, name, algo, params) VALUES
    (NULL, 'data-structured', 'data',
     '{"child_target_tokens":512,"floor_tokens":64,"overlap_tokens":0,"breadcrumb_depth":-1}'::jsonb)
ON CONFLICT DO NOTHING;

UPDATE chunking_category_strategies
SET strategy_name = 'data-structured'
WHERE category = 'data' AND workspace_id IS NULL;
