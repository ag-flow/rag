-- Migration 084 — catalogue LLM pour l'enrichissement de chunks
--
-- Critère : rapport coût/qualité en batch (résumés, mots-clés, métadonnées),
-- pas la puissance frontier. Providers câblés dans services/llm_clients :
--   openai    → API OpenAI directe
--   claude    → API Anthropic directe
--   gemini    → endpoint OpenAI-compatible Google
--   deepseek  → https://api.deepseek.com/v1 (OpenAI-compatible)
--   dashscope → https://dashscope-intl.aliyuncs.com/compatible-mode/v1
-- `service` aligné sur service_for_provider (inutilisé pour kind='llm').

INSERT INTO model_dimensions (provider, model, dimension, kind, service) VALUES
    -- OpenAI — gpt-4.1-nano : le moins cher, idéal enrichissement batch.
    ('openai', 'gpt-4.1-nano', NULL, 'llm', 'openai'),
    ('openai', 'gpt-4.1-mini', NULL, 'llm', 'openai'),
    ('openai', 'gpt-4.1',      NULL, 'llm', 'openai'),
    -- Anthropic — haiku pour l'extraction structurée rapide, sonnet quand le
    -- prompt système constant profite du prompt caching (-90 % input).
    ('claude', 'claude-haiku-4-5',  NULL, 'llm', 'openai'),
    ('claude', 'claude-sonnet-4-6', NULL, 'llm', 'openai'),
    -- Google Gemini — flash : meilleur rapport qualité/prix pour le batch.
    ('gemini', 'gemini-2.5-flash', NULL, 'llm', 'gemini'),
    ('gemini', 'gemini-3-flash',   NULL, 'llm', 'gemini'),
    ('gemini', 'gemini-3.5-flash', NULL, 'llm', 'gemini'),
    -- DeepSeek — v4-flash : open weights, ultra-cheap, contexte 1M.
    ('deepseek', 'deepseek-v4-flash', NULL, 'llm', 'openai'),
    ('deepseek', 'deepseek-v4-pro',   NULL, 'llm', 'openai'),
    -- Alibaba DashScope (déjà présent côté embeddings).
    ('dashscope', 'qwen3.7-max', NULL, 'llm', 'dashscope'),
    ('dashscope', 'qwen3-plus',  NULL, 'llm', 'dashscope')
ON CONFLICT (provider, model) DO NOTHING;
