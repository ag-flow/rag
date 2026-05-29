-- Migration 022 — modèles Ollama supplémentaires
--
-- nomic-embed-text:v1.5 : version améliorée (contexte 8192 tokens, surpasse ada-002).
-- qwen3-embedding-0.6b  : modèle Alibaba léger, MRL configurable 32–1024 dim.
-- qwen3-embedding-8b    : modèle Alibaba haute qualité, 4096 dim.

INSERT INTO model_dimensions (provider, model, dimension) VALUES
    ('ollama', 'nomic-embed-text:v1.5',  768),
    ('ollama', 'qwen3-embedding-0.6b',  1024),
    ('ollama', 'qwen3-embedding-8b',    4096)
ON CONFLICT DO NOTHING;
