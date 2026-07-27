-- Migration 064 — model_dimensions : rattachement des modèles à un utilisateur
--
-- Les modèles ajoutés via l'IHM/API appartiennent désormais à leur créateur
-- (owner_id TEXT, convention sha256(email) — même pattern que
-- chunking_strategies / prompt_templates / user_api_keys).
-- owner_id NULL = catalogue système (seeds des migrations), visible par tous
-- et immuable.
--
-- L'unicité GLOBALE (provider, model) est conservée : toutes les jointures
-- de résolution (indexer_configs → model_dimensions sur (provider, model))
-- doivent rester non ambiguës. Conséquence assumée : un 409 à la création
-- peut référencer un modèle appartenant à un autre utilisateur.
--
-- Les lignes existantes ajoutées à la main avant cette migration deviennent
-- système (identité du créateur non tracée jusqu'ici).

ALTER TABLE model_dimensions ADD COLUMN owner_id TEXT NULL;

COMMENT ON COLUMN model_dimensions.owner_id IS
    'sha256(email) du créateur ; NULL = catalogue système (immuable)';
