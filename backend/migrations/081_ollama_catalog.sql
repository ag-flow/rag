-- Migration 081 — catalogue Ollama : local (< 12 Go) et cloud
--
-- Deux catégories dans le registre des modèles :
--   provider 'ollama'       → modèles exécutables en local avec < 12 Go de
--                             VRAM (tag le plus gros de chaque famille qui
--                             tient sous la limite, quantization Q4 par défaut)
--   provider 'ollama-cloud' → modèles hébergés par Ollama Cloud
--                             (https://ollama.com, clé API requise) ; tags
--                             ':cloud' pour les cloud-only, '<taille>-cloud'
--                             pour les familles hybrides.
-- Catalogue relevé sur https://ollama.com/library le 2026-07-26.
-- Ollama Cloud ne propose ni modèle d'embedding ni reranker à cette date.

-- ── Ollama local — embedding (dimension vérifiée par famille) ───────────────
INSERT INTO model_dimensions (provider, model, dimension, kind) VALUES
    ('ollama', 'nomic-embed-text',           768,  'embedding'),
    ('ollama', 'nomic-embed-text-v2-moe',    768,  'embedding'),
    ('ollama', 'mxbai-embed-large',          1024, 'embedding'),
    ('ollama', 'bge-m3',                     1024, 'embedding'),
    ('ollama', 'bge-large',                  1024, 'embedding'),
    ('ollama', 'snowflake-arctic-embed',     1024, 'embedding'),
    ('ollama', 'snowflake-arctic-embed2',    1024, 'embedding'),
    ('ollama', 'all-minilm',                 384,  'embedding'),
    ('ollama', 'paraphrase-multilingual',    768,  'embedding'),
    ('ollama', 'granite-embedding',          768,  'embedding'),
    ('ollama', 'embeddinggemma',             768,  'embedding'),
    ('ollama', 'qwen3-embedding:0.6b',       1024, 'embedding'),
    ('ollama', 'qwen3-embedding:4b',         2560, 'embedding'),
    ('ollama', 'qwen3-embedding:8b',         4096, 'embedding')
ON CONFLICT (provider, model) DO NOTHING;

-- ── Ollama local — LLM (< 12 Go) ─────────────────────────────────────────────
INSERT INTO model_dimensions (provider, model, dimension, kind) VALUES
    ('ollama', 'llama3.1:8b',          NULL, 'llm'),
    ('ollama', 'llama3.2:3b',          NULL, 'llm'),
    ('ollama', 'gemma3:12b',           NULL, 'llm'),
    ('ollama', 'gemma4:12b',           NULL, 'llm'),
    ('ollama', 'qwen3:14b',            NULL, 'llm'),
    ('ollama', 'qwen3.5:9b',           NULL, 'llm'),
    ('ollama', 'qwen2.5:14b',          NULL, 'llm'),
    ('ollama', 'qwen2.5-coder:14b',    NULL, 'llm'),
    ('ollama', 'deepseek-r1:14b',      NULL, 'llm'),
    ('ollama', 'deepseek-coder-v2:16b', NULL, 'llm'),
    ('ollama', 'mistral:7b',           NULL, 'llm'),
    ('ollama', 'mistral-nemo:12b',     NULL, 'llm'),
    ('ollama', 'ministral-3:14b',      NULL, 'llm'),
    ('ollama', 'phi4:14b',             NULL, 'llm'),
    ('ollama', 'phi4-mini:3.8b',       NULL, 'llm'),
    ('ollama', 'glm4:9b',              NULL, 'llm'),
    ('ollama', 'granite4.1:8b',        NULL, 'llm'),
    ('ollama', 'nemotron-3-nano:4b',   NULL, 'llm')
ON CONFLICT (provider, model) DO NOTHING;

-- ── Ollama cloud — LLM ───────────────────────────────────────────────────────
INSERT INTO model_dimensions (provider, model, dimension, kind) VALUES
    ('ollama-cloud', 'gemma4:cloud',              NULL, 'llm'),
    ('ollama-cloud', 'qwen3.5:cloud',             NULL, 'llm'),
    ('ollama-cloud', 'glm-5.1:cloud',             NULL, 'llm'),
    ('ollama-cloud', 'glm-5.2:cloud',             NULL, 'llm'),
    ('ollama-cloud', 'minimax-m2.5:cloud',        NULL, 'llm'),
    ('ollama-cloud', 'minimax-m2.7:cloud',        NULL, 'llm'),
    ('ollama-cloud', 'minimax-m3:cloud',          NULL, 'llm'),
    ('ollama-cloud', 'nemotron-3-super:cloud',    NULL, 'llm'),
    ('ollama-cloud', 'nemotron-3-ultra:cloud',    NULL, 'llm'),
    ('ollama-cloud', 'nemotron-3-nano:30b-cloud', NULL, 'llm'),
    ('ollama-cloud', 'kimi-k2.5:cloud',           NULL, 'llm'),
    ('ollama-cloud', 'kimi-k2.6:cloud',           NULL, 'llm'),
    ('ollama-cloud', 'kimi-k2.7-code:cloud',      NULL, 'llm'),
    ('ollama-cloud', 'deepseek-v4-pro:cloud',     NULL, 'llm'),
    ('ollama-cloud', 'deepseek-v4-flash:cloud',   NULL, 'llm'),
    ('ollama-cloud', 'gpt-oss:20b-cloud',         NULL, 'llm'),
    ('ollama-cloud', 'gpt-oss:120b-cloud',        NULL, 'llm'),
    ('ollama-cloud', 'gemini-3-flash-preview:cloud', NULL, 'llm'),
    ('ollama-cloud', 'mistral-large-3:cloud',     NULL, 'llm')
ON CONFLICT (provider, model) DO NOTHING;
