-- Migration 088 — Cohere Rerank v4.0 sur Azure AI Foundry + préco pipeline Azure
--
-- Le catalogue Foundry (relevé 2026-07-26) propose la génération v4.0 :
-- Cohere-rerank-v4.0-fast (latence/coût — recommandé pour rescorer le top-k)
-- et Cohere-rerank-v4.0-pro (qualité max). Le champ `model` est informatif
-- pour un déploiement serverless (l'URL du déploiement porte le modèle).

INSERT INTO model_dimensions (provider, model, dimension, kind, service) VALUES
    ('azure-foundry', 'Cohere-rerank-v4.0-fast', NULL, 'rerank', 'openai'),
    ('azure-foundry', 'Cohere-rerank-v4.0-pro',  NULL, 'rerank', 'openai')
ON CONFLICT (provider, model) DO NOTHING;

-- Préco : embeddings OpenAI servis par Azure + Cohere Rerank (même pipeline
-- éprouvé que openai + cohere — LlamaIndex), y compris via Azure Foundry.
INSERT INTO rerank_pairings
    (embed_provider_like, embed_model_like, rerank_provider_like, rerank_model_like, note)
VALUES
    ('azure-openai', 'text-embedding-3-%', 'azure-foundry', 'Cohere-rerank-%',
     'Pipeline 100 % Azure : OpenAI embeddings + Cohere Rerank (meilleurs hit rate/MRR)'),
    ('azure-openai', 'text-embedding-3-%', 'cohere', 'rerank-%',
     'OpenAI embeddings (via Azure) + Cohere Rerank direct : meilleurs hit rate/MRR (LlamaIndex)');
