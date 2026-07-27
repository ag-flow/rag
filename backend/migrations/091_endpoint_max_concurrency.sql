-- Migration 091 — limite de requêtes parallèles par service d'endpoint
--
-- Enabler a7e2ec90 : le throttling s'applique AU NIVEAU DE L'ENDPOINT,
-- agrégé sur tous les workspaces qui le partagent (la limite protège le
-- fournisseur). NULL = pas de limite. L'enforcement (fenêtres rpm/tpm de la
-- migration 087 + ce sémaphore) est in-process, clé (endpoint, service) —
-- services/endpoint_throttle.py.

ALTER TABLE vault_endpoints
    ADD COLUMN indexer_max_concurrency INT,
    ADD COLUMN rerank_max_concurrency INT,
    ADD COLUMN llm_max_concurrency INT;

ALTER TABLE vault_endpoints
    ADD CONSTRAINT vault_endpoints_max_concurrency_positive
    CHECK (
        (indexer_max_concurrency IS NULL OR indexer_max_concurrency >= 1)
        AND (rerank_max_concurrency IS NULL OR rerank_max_concurrency >= 1)
        AND (llm_max_concurrency IS NULL OR llm_max_concurrency >= 1)
    );
