-- Migration 021 — nouveaux modèles d'embedding 2026
--
-- voyage-3-lite  : plus rapide et moins cher que voyage-3, bon pour le prototypage.
-- voyage-multilingual-2 : optimisé multilingue (docs non-anglophones).
-- bge-m3 (Ollama) : modèle BAAI, multilingue, performant en retrieval.

INSERT INTO model_dimensions (provider, model, dimension) VALUES
    ('voyage', 'voyage-3-lite',         512),
    ('voyage', 'voyage-multilingual-2', 1024),
    ('ollama', 'bge-m3',               1024)
ON CONFLICT DO NOTHING;
