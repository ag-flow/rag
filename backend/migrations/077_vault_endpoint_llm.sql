-- Migration 077 — le LLM rejoint le préréglage endpoint (3e service IA)
--
-- Un endpoint paramètre désormais les TROIS services IA d'un workspace :
-- vectorisation (embedding), reranking, et LLM (exécution des prompts :
-- enrichissements, contexte de chunks, chat Playground). À la création d'un
-- workspace depuis un endpoint, la config LLM est copiée dans
-- workspace_llm_configs (même modèle snapshot que indexer/rerank).

ALTER TABLE vault_endpoints
    ADD COLUMN llm_provider    TEXT,
    ADD COLUMN llm_model       TEXT,
    ADD COLUMN llm_api_key_ref TEXT,
    ADD COLUMN llm_base_url    TEXT;
