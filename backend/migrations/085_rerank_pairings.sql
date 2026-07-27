-- Migration 085 — préconisations de pairing embedder → reranker
--
-- Un reranker fonctionne avec n'importe quel embedder (il rescore des paires
-- query+document en texte brut), mais certains couples sont validés :
-- même famille (pipeline conçu ensemble) ou cross-provider éprouvé.
-- L'IHM affiche « préco » sur les rerankers qui matchent l'embedder choisi.
--
-- Sémantique des motifs : LIKE SQL insensible à la casse ('%' = joker),
-- évalué côté client sur (provider, model) de chaque côté.

CREATE TABLE rerank_pairings (
    id                     SERIAL PRIMARY KEY,
    embed_provider_like    TEXT NOT NULL,
    embed_model_like       TEXT NOT NULL,
    rerank_provider_like   TEXT NOT NULL,
    rerank_model_like      TEXT NOT NULL,
    note                   TEXT NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO rerank_pairings
    (embed_provider_like, embed_model_like, rerank_provider_like, rerank_model_like, note)
VALUES
    -- Même famille : conçus pour fonctionner ensemble.
    ('cohere', 'embed-%', 'cohere', 'rerank-%',
     'Pipeline deux étages intégré Cohere (input_type optimisé pour le reranking)'),
    ('%', '%qwen3-embedding%', '%', '%qwen3-reranker%',
     'Même famille Qwen3 : embedding + reranker conçus en pipeline, tailles modulables'),
    ('%', '%bge-m3', 'ollama', 'bge-reranker-v2-m3',
     'Standard de facto self-hosted : couple BGE-M3 + bge-reranker-v2-m3 (Apache 2.0)'),
    ('voyage', '%', 'voyage', '%',
     'Bundle mono-provider Voyage (variantes code/legal : +2-4 NDCG@10 sur ces domaines)'),
    ('jina', '%', 'jina', '%',
     'Même provider Jina (v3 : function-calling, code search — licence CC-BY-NC)'),
    -- Cross-provider éprouvés.
    ('openai', 'text-embedding-3-%', 'cohere', 'rerank-%',
     'OpenAI embeddings + Cohere Rerank : meilleurs hit rate et MRR combinés (LlamaIndex)'),
    ('%', '%bge-m3', 'deepinfra', 'Qwen/Qwen3-Reranker-4B',
     'Qwen3-Reranker-4B améliore toutes les configurations d''embedding testées (arXiv)');
