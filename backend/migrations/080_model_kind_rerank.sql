-- Migration 080 — le registre des modèles accueille les RERANKERS (kind)
--
-- La page Models gère désormais les TROIS besoins d'un endpoint :
-- embedding (avec dimension), llm et rerank (sans dimension). L'onglet
-- Rerank d'un endpoint liste les modèles kind='rerank' du provider choisi
-- — la table des modèles reste le référentiel UNIQUE (plus de liste codée
-- en dur côté IHM).

ALTER TABLE model_dimensions DROP CONSTRAINT model_dimensions_kind_check;
ALTER TABLE model_dimensions ADD CONSTRAINT model_dimensions_kind_check
    CHECK (kind IN ('embedding', 'llm', 'rerank'));

ALTER TABLE model_dimensions DROP CONSTRAINT model_dimensions_dimension_check;
ALTER TABLE model_dimensions ADD CONSTRAINT model_dimensions_dimension_check
    CHECK (
        (kind = 'embedding' AND dimension IS NOT NULL AND dimension > 0)
        OR (kind IN ('llm', 'rerank') AND dimension IS NULL)
    );

-- Seed système : reprend la liste jusqu'ici codée en dur dans l'IHM
-- (WorkspaceRerankTab.schema.ts) pour que les listes ne soient pas vides.
INSERT INTO model_dimensions (provider, model, dimension, kind) VALUES
    ('cohere', 'rerank-v3.5', NULL, 'rerank'),
    ('cohere', 'rerank-english-v3.0', NULL, 'rerank'),
    ('cohere', 'rerank-multilingual-v3.0', NULL, 'rerank'),
    ('cohere', 'rerank-english-light-v3.0', NULL, 'rerank'),
    ('cohere', 'rerank-multilingual-light-v3.0', NULL, 'rerank'),
    ('voyage', 'voyage-rerank-2', NULL, 'rerank'),
    ('voyage', 'voyage-rerank-2-lite', NULL, 'rerank'),
    ('voyage', 'voyage-rerank-1', NULL, 'rerank'),
    ('jina', 'jina-reranker-v2-base-multilingual', NULL, 'rerank'),
    ('jina', 'jina-reranker-v1-base-en', NULL, 'rerank'),
    ('jina', 'jina-colbert-v2', NULL, 'rerank'),
    ('dashscope', 'gte-rerank-v2', NULL, 'rerank'),
    ('dashscope', 'gte-rerank', NULL, 'rerank'),
    ('azure-foundry', 'rerank-v3.5', NULL, 'rerank'),
    ('azure-foundry', 'rerank-multilingual-v3.0', NULL, 'rerank'),
    ('azure-foundry', 'rerank-english-v3.0', NULL, 'rerank'),
    ('ollama', 'bge-reranker-v2-m3', NULL, 'rerank'),
    ('ollama', 'bge-reranker-base', NULL, 'rerank'),
    ('ollama', 'ms-marco-minilm', NULL, 'rerank')
ON CONFLICT (provider, model) DO NOTHING;
