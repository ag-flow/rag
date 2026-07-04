-- Corrige le seed global code-aware : overlap cross-symbole = bruit sémantique.
-- tree-sitter découpe aux frontières naturelles (fonction/classe/méthode) ;
-- le breadcrumb de portée (module > classe > méthode) fournit déjà le contexte.
-- N'affecte pas les surcharges workspace-level existantes.
UPDATE chunking_strategies
SET params = params || '{"overlap_tokens": 0}'::jsonb
WHERE workspace_id IS NULL
  AND name = 'code-aware';
