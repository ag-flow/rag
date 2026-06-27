-- Migration 036 — modèles d'embedding DashScope (Alibaba Qwen)
--
-- text-embedding-v3 : génération précédente, dim 1024, gratuit 500K tokens/90j.
-- text-embedding-v4 : génération courante, dim flexible 64–2048 (défaut 1024), gratuit 1M tokens/90j.
-- Provider slug : "dashscope"

INSERT INTO model_dimensions (provider, model, dimension) VALUES
    ('dashscope', 'text-embedding-v3', 1024),
    ('dashscope', 'text-embedding-v4', 1024)
ON CONFLICT DO NOTHING;
