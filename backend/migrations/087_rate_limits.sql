-- Migration 087 — limites de débit par service IA (RPM / TPM)
--
-- Les providers cloud imposent des rate limits par déploiement (ex. Azure :
-- 3000 req/min, 500k tokens/min). L'endpoint porte les règles PAR SERVICE
-- (vectorisation / rerank / llm) ; convention : NULL = règle désactivée,
-- valeur = limite active. Copiées dans la config du workspace à la création
-- et lors de « Rafraîchir depuis l'endpoint ».

ALTER TABLE vault_endpoints
    ADD COLUMN indexer_rpm_limit INTEGER CHECK (indexer_rpm_limit > 0),
    ADD COLUMN indexer_tpm_limit INTEGER CHECK (indexer_tpm_limit > 0),
    ADD COLUMN rerank_rpm_limit  INTEGER CHECK (rerank_rpm_limit > 0),
    ADD COLUMN rerank_tpm_limit  INTEGER CHECK (rerank_tpm_limit > 0),
    ADD COLUMN llm_rpm_limit     INTEGER CHECK (llm_rpm_limit > 0),
    ADD COLUMN llm_tpm_limit     INTEGER CHECK (llm_tpm_limit > 0);

-- Copies côté workspace (snapshot par service).
ALTER TABLE indexer_configs
    ADD COLUMN rpm_limit INTEGER CHECK (rpm_limit > 0),
    ADD COLUMN tpm_limit INTEGER CHECK (tpm_limit > 0);

ALTER TABLE rerank_configs
    ADD COLUMN rpm_limit INTEGER CHECK (rpm_limit > 0),
    ADD COLUMN tpm_limit INTEGER CHECK (tpm_limit > 0);

ALTER TABLE workspace_llm_configs
    ADD COLUMN rpm_limit INTEGER CHECK (rpm_limit > 0),
    ADD COLUMN tpm_limit INTEGER CHECK (tpm_limit > 0);
