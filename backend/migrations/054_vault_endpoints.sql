-- Migration 054 — endpoints de vectorisation portés par les coffres
--
-- Un « endpoint » est un préréglage nommé (label + slug auto-calculé) qui
-- regroupe la configuration de vectorisation (provider/modèle/clé/base_url)
-- et, optionnellement, celle du reranking. Les workspaces se créent ensuite
-- en choisissant un endpoint : sa config est COPIÉE dans indexer_configs /
-- rerank_configs (snapshot à la création — modifier l'endpoint n'affecte que
-- les futurs workspaces).

CREATE TABLE vault_endpoints (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vault_id             UUID NOT NULL REFERENCES harpocrate_vaults(id) ON DELETE CASCADE,
    label                TEXT NOT NULL,
    slug                 TEXT NOT NULL,
    indexer_provider     TEXT NOT NULL,
    indexer_model        TEXT NOT NULL,
    indexer_api_key_ref  TEXT,
    indexer_base_url     TEXT,
    rerank_provider      TEXT,
    rerank_model         TEXT,
    rerank_api_key_ref   TEXT,
    rerank_base_url      TEXT,
    rerank_top_k         INTEGER,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (vault_id, slug)
);

CREATE INDEX vault_endpoints_vault ON vault_endpoints (vault_id);
