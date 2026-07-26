-- Migration 082 — catalogue d'embeddings cloud + rattrapage de la colonne service
--
-- 1) Rattrapage : les inserts récents (081, ajouts via la page Models) ne
--    renseignaient pas `service` (capacité IA routée par la factory,
--    cf. 037). Un service vide casse make_provider à l'indexation.
-- 2) Nouveaux providers cloud d'embedding, tous OpenAI-compatibles côté API
--    (service='openai') sauf Bedrock (service='bedrock', auth AWS SigV4 non
--    câblée à ce jour — sélectionnable mais non indexable, alerte en place).
--    URLs directes ajoutées dans factory._DIRECT_URLS : fireworks, deepinfra,
--    together, cohere (endpoint /compatibility/v1).

-- ── Rattrapage service ───────────────────────────────────────────────────────
UPDATE model_dimensions SET service = provider
    WHERE service = ''
      AND provider IN ('ollama', 'openai', 'voyage', 'mistral', 'jina', 'gemini', 'dashscope');
UPDATE model_dimensions SET service = 'openai'
    WHERE service = '' AND provider IN ('azure-openai', 'azure-foundry');
-- 'ollama-cloud' (081, kind llm) : service inutilisé pour les LLM mais on
-- reste cohérent.
UPDATE model_dimensions SET service = 'ollama'
    WHERE service = '' AND provider = 'ollama-cloud';

-- ── Cohere (API compatibilité OpenAI) ────────────────────────────────────────
-- embed-v4 : Matryoshka 256–1536, on provisionne la dimension par défaut 1536.
INSERT INTO model_dimensions (provider, model, dimension, kind, service, max_input_tokens) VALUES
    ('cohere', 'embed-v4',              1536, 'embedding', 'openai', 128000),
    ('cohere', 'embed-english-v3.0',    1024, 'embedding', 'openai', 512),
    ('cohere', 'embed-multilingual-v3.0', 1024, 'embedding', 'openai', 512)
ON CONFLICT (provider, model) DO NOTHING;

-- ── Fireworks AI (serverless, OpenAI-compatible) ─────────────────────────────
-- Les ids de modèles Fireworks sont des chemins complets.
INSERT INTO model_dimensions (provider, model, dimension, kind, service, max_input_tokens) VALUES
    ('fireworks', 'accounts/fireworks/models/qwen3-embedding-8b', 4096, 'embedding', 'openai', 32768),
    ('fireworks', 'nomic-ai/nomic-embed-text-v1.5',               768,  'embedding', 'openai', 8192),
    ('fireworks', 'nomic-ai/nomic-embed-text-v1',                 768,  'embedding', 'openai', 8192)
ON CONFLICT (provider, model) DO NOTHING;

-- ── DeepInfra (OpenAI-compatible) ────────────────────────────────────────────
-- Qwen3-Embedding-4B : dimension NATIVE 2560 (la fiche fournie disait 2048).
INSERT INTO model_dimensions (provider, model, dimension, kind, service, max_input_tokens) VALUES
    ('deepinfra', 'Qwen/Qwen3-Embedding-8B',          4096, 'embedding', 'openai', 32768),
    ('deepinfra', 'Qwen/Qwen3-Embedding-4B',          2560, 'embedding', 'openai', 32768),
    ('deepinfra', 'BAAI/bge-m3',                      1024, 'embedding', 'openai', 8192),
    ('deepinfra', 'BAAI/bge-large-en-v1.5',           1024, 'embedding', 'openai', 512),
    ('deepinfra', 'intfloat/e5-base-v2',              768,  'embedding', 'openai', 512),
    ('deepinfra', 'nvidia/Nemotron-3-Embed-8B-BF16',  4096, 'embedding', 'openai', 32768)
ON CONFLICT (provider, model) DO NOTHING;

-- ── Together AI (OpenAI-compatible) ──────────────────────────────────────────
INSERT INTO model_dimensions (provider, model, dimension, kind, service, max_input_tokens) VALUES
    ('together', 'BAAI/bge-large-en-v1.5',                       1024, 'embedding', 'openai', 512),
    ('together', 'intfloat/multilingual-e5-large-instruct',      1024, 'embedding', 'openai', 512),
    ('together', 'togethercomputer/m2-bert-80M-8k-retrieval',    768,  'embedding', 'openai', 8192),
    ('together', 'togethercomputer/m2-bert-80M-32k-retrieval',   768,  'embedding', 'openai', 32768)
ON CONFLICT (provider, model) DO NOTHING;

-- ── AWS Bedrock (auth SigV4 — adapter non câblé, chantier séparé) ────────────
INSERT INTO model_dimensions (provider, model, dimension, kind, service, max_input_tokens) VALUES
    ('bedrock', 'amazon.titan-embed-text-v2:0', 1024, 'embedding', 'bedrock', 8192),
    ('bedrock', 'amazon.titan-embed-image-v1',  1024, 'embedding', 'bedrock', 8192),
    ('bedrock', 'cohere.embed-v4:0',            1536, 'embedding', 'bedrock', 128000)
ON CONFLICT (provider, model) DO NOTHING;
