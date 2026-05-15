-- Migration 008 — model_dimensions : ajout mxbai-embed-large (Ollama, 1024 dim)
-- Requis pour le smoke E2E Ollama (mxbai-embed-large disponible sur homelab LXC 80).

INSERT INTO model_dimensions (provider, model, dimension) VALUES
    ('ollama', 'mxbai-embed-large', 1024)
ON CONFLICT DO NOTHING;
