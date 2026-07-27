-- Migration 083 — rerankers cloud : fireworks, deepinfra, mixedbread
--
-- Complète la couche Reranking du registre (kind='rerank', pas de dimension).
-- Les trois plateformes sont câblées dans rag.rerank.providers.factory :
--   fireworks  → POST /rerank (format Cohere), ids en chemins complets
--   deepinfra  → POST /v1/inference/{model} par paires {queries, documents}
--   mixedbread → POST /v1/reranking (champ `input`, réponse data[].score)
-- `service` est renseigné par cohérence avec service_for_provider (inutilisé
-- pour le rerank, qui route par provider).

INSERT INTO model_dimensions (provider, model, dimension, kind, service) VALUES
    ('fireworks', 'accounts/fireworks/models/qwen3-reranker-8b', NULL, 'rerank', 'openai'),
    ('deepinfra', 'Qwen/Qwen3-Reranker-8B',                      NULL, 'rerank', 'openai'),
    ('deepinfra', 'Qwen/Qwen3-Reranker-4B',                      NULL, 'rerank', 'openai'),
    ('deepinfra', 'nvidia/llama-nemotron-rerank-vl-1b-v2',       NULL, 'rerank', 'openai'),
    ('mixedbread', 'mxbai-rerank-large-v2',                      NULL, 'rerank', 'openai'),
    ('mixedbread', 'mxbai-rerank-base-v2',                       NULL, 'rerank', 'openai')
ON CONFLICT (provider, model) DO NOTHING;
