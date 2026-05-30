-- Migration 023 — modeles Mistral AI + Jina AI
--
-- mistral-embed        : modele texte general Mistral (1024 dim).
-- codestral-embed-2505 : specialise code, concurrent voyage-code-3 (3072 dim).
-- jina-embeddings-v3   : multilingue 100+ langues, MRL, contexte 8192 tokens (1024 dim).

INSERT INTO model_dimensions (provider, model, dimension) VALUES
    ('mistral', 'mistral-embed',         1024),
    ('mistral', 'codestral-embed-2505',  3072),
    ('jina',    'jina-embeddings-v3',    1024)
ON CONFLICT DO NOTHING;
