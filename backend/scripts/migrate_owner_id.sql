-- Reprise owner_id — bascule du pivot preferred_username → email (chantier profil)
--
-- CONTEXTE : owner_id = sha256(principal). Avant le chantier profil, la session
-- OIDC dérivait le principal de `preferred_username` ; désormais c'est l'EMAIL
-- (pivot unique, table users). Un utilisateur OIDC dont preferred_username ≠
-- email obtient donc un NOUVEL owner_id : ses objets existants doivent être
-- repris une fois, à l'exécution manuelle de ce script.
--
-- USAGE (psql, base rag_config) :
--   \set ancien  'sha256 de l''ancien principal (preferred_username, minuscule)'
--   \set nouveau 'sha256 du nouveau principal (email, minuscule)'
--   Exemple de calcul : echo -n 'gael' | sha256sum ; echo -n 'gael@corp.example' | sha256sum
--
-- Puis :
--   psql ... -v ancien=<hash> -v nouveau=<hash> -f migrate_owner_id.sql
--
-- Idempotent : re-exécuter ne change rien si l'ancien hash n'existe plus.

BEGIN;

UPDATE workspaces          SET owner_id = :'nouveau' WHERE owner_id = :'ancien';
UPDATE chunking_strategies SET owner_id = :'nouveau' WHERE owner_id = :'ancien';
UPDATE prompt_templates    SET owner_id = :'nouveau' WHERE owner_id = :'ancien';
UPDATE user_api_keys       SET owner_id = :'nouveau' WHERE owner_id = :'ancien';

-- Récapitulatif.
SELECT 'workspaces'          AS table_name, count(*) AS lignes FROM workspaces          WHERE owner_id = :'nouveau'
UNION ALL
SELECT 'chunking_strategies', count(*) FROM chunking_strategies WHERE owner_id = :'nouveau'
UNION ALL
SELECT 'prompt_templates',    count(*) FROM prompt_templates    WHERE owner_id = :'nouveau'
UNION ALL
SELECT 'user_api_keys',       count(*) FROM user_api_keys       WHERE owner_id = :'nouveau';

COMMIT;
