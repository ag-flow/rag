-- Migration 076 — répare les params des stratégies code/data (résidu de la 042)
--
-- La 042 a basculé la stratégie SYSTÈME 'code-aware' de l'algo 'prose' vers
-- 'code' SANS retirer 'heading_levels' de ses params (posé au seed 040, valide
-- en prose, inconnu pour code). Depuis, tout chunking qui la résout (cascade
-- catégorie 'code', cibles de routes de régions) échoue à l'exécution :
--   ValueError: unknown params for algo 'code': ['heading_levels']
-- Les duplications de cette stratégie ont propagé le param invalide.
--
-- 'heading_levels' est la seule clé prose inconnue des algos code/data
-- (breadcrumb_depth est commun) : retrait généralisé, aucun autre param touché.

UPDATE chunking_strategies
SET params = params - 'heading_levels', updated_at = now()
WHERE algo IN ('code', 'data') AND params ? 'heading_levels';
