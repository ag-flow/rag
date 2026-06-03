-- Migration 035 — modèle d'embedding Google Gemini
--
-- gemini-embedding-001 : modèle de référence Gemini (3072 dim, top MTEB).
-- Endpoint OpenAI-compatible : generativelanguage.googleapis.com/v1beta/openai/embeddings
-- Provider slug : "gemini"

INSERT INTO model_dimensions (provider, model, dimension) VALUES
    ('gemini', 'gemini-embedding-001', 3072)
ON CONFLICT DO NOTHING;
