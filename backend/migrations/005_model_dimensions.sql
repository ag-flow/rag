-- Migration 005 — model_dimensions : registry des couples (provider, model)
-- supportés par le service RAG, avec leur dimension d'embedding.
-- Alimentable runtime via les endpoints POST/DELETE /admin/models (M2).

CREATE TABLE IF NOT EXISTS model_dimensions (
    provider    TEXT NOT NULL,
    model       TEXT NOT NULL,
    dimension   INT  NOT NULL CHECK (dimension > 0),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, model)
);

INSERT INTO model_dimensions (provider, model, dimension) VALUES
    ('openai', 'text-embedding-3-small', 1536),
    ('openai', 'text-embedding-3-large', 3072),
    ('voyage', 'voyage-3', 1024),
    ('voyage', 'voyage-code-3', 1024),
    ('ollama', 'qwen2.5-coder:14b', 4096),
    ('ollama', 'nomic-embed-text', 768)
ON CONFLICT DO NOTHING;
