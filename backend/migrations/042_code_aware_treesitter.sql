-- Migration 042 — Lot 2 : la stratégie globale 'code-aware' passe à l'algo
-- 'code' (tree-sitter) au lieu de 'prose'.
--
-- Effet : pour un workspace en moteur 'structured', les fichiers de catégorie
-- 'code' seront désormais découpés par symboles (tree-sitter) avec fallback
-- prose si le langage n'est pas supporté. Le texte embeddé change → une
-- réindexation est nécessaire pour répercuter (le diff par chunk_hash ne
-- ré-embed que les chunks réellement modifiés).

UPDATE chunking_strategies
SET algo = 'code', updated_at = now()
WHERE name = 'code-aware' AND workspace_id IS NULL;
