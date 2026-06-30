-- Relève le floor minimum pour les chunks code-aware.
-- 64 tokens (~256 chars) capture des micro-stubs sans valeur (pass, return None,
-- commentaires isolés). 128 tokens (~512 chars) filtre le bruit tout en
-- conservant les petites fonctions significatives.
-- N'affecte pas les surcharges workspace-level existantes.
UPDATE chunking_strategies
SET params = params || '{"floor_tokens": 128}'::jsonb
WHERE workspace_id IS NULL
  AND name = 'code-aware';
