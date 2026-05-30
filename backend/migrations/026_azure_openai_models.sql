-- Migration 026 — modèles Azure OpenAI Embeddings

INSERT INTO model_dimensions (provider, model, dimension) VALUES
    ('azure-openai', 'text-embedding-3-small', 1536),
    ('azure-openai', 'text-embedding-3-large', 3072),
    ('azure-openai', 'text-embedding-ada-002', 1536)
ON CONFLICT DO NOTHING;
