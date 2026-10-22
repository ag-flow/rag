-- Migration 096 — catalogue Mammouth AI (agrégateur hébergé en France, RGPD)
--
-- API OpenAI-compatible à https://api.mammouth.ai/v1, auth Bearer : service
-- 'openai' côté factory (embeddings) et llm_clients (chat). Pas de rerank.
-- Liste LLM curatée pour l'usage RAG (ticket backlog 04d7a7ca), pas le
-- catalogue complet (~110 modèles, GET /public/models). Les tarifs vivent
-- dans pricing.yml, jamais ici.
-- max_input_tokens : relevé /public/models du 2026-10-18.

INSERT INTO model_dimensions (provider, model, dimension, kind, service, max_input_tokens) VALUES
    ('mammouth', 'text-embedding-3-large', 3072, 'embedding', 'openai', 8191),
    ('mammouth', 'text-embedding-3-small', 1536, 'embedding', 'openai', 8191)
ON CONFLICT (provider, model) DO NOTHING;

INSERT INTO model_dimensions (provider, model, dimension, kind, service) VALUES
    -- Alias dynamique : Mammouth choisit le modèle servi, le coût varie.
    ('mammouth', 'mammouth-recommended', NULL, 'llm', 'openai'),
    ('mammouth', 'mistral-medium-3.1',   NULL, 'llm', 'openai'),
    ('mammouth', 'mistral-small-2603',   NULL, 'llm', 'openai'),
    ('mammouth', 'deepseek-v4-flash',    NULL, 'llm', 'openai'),
    ('mammouth', 'deepseek-v4-pro',      NULL, 'llm', 'openai'),
    ('mammouth', 'claude-sonnet-4-6',    NULL, 'llm', 'openai'),
    ('mammouth', 'gpt-5.1',              NULL, 'llm', 'openai'),
    ('mammouth', 'gemini-2.5-flash',     NULL, 'llm', 'openai'),
    ('mammouth', 'qwen3-coder',          NULL, 'llm', 'openai')
ON CONFLICT (provider, model) DO NOTHING;
