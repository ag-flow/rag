-- Migration 092 — banc de test de recherche intégré au produit
--
-- Feature 1a9b8b67 (spec architecte 2026-07-27) : les questions de test et
-- leur réponse attendue sont poussées par les agents via MCP, consultées et
-- lancées depuis l'IHM (onglet workspace), les runs et leurs résultats sont
-- persistés — remplace le flux fichier YAML du protocole D9.

CREATE TABLE search_test_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    -- Fragment attendu dans le path des résultats (ex. UUID docflow du doc
    -- source) : le scoring est un test mécanique de provenance (D9).
    expected_path_contains TEXT NOT NULL,
    family TEXT NOT NULL DEFAULT 'libre'
        CHECK (family IN ('litterale', 'paraphrasee', 'indirecte', 'libre')),
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, question)
);

CREATE TABLE search_test_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Config testée au moment du run (hybride, moteur, pondérations, top_k).
    config JSONB NOT NULL,
    -- Métriques agrégées : recall@1/5/10, mrr — globales et par famille.
    metrics JSONB NOT NULL,
    questions_total INT NOT NULL,
    questions_failed INT NOT NULL
);

CREATE INDEX idx_search_test_runs_ws ON search_test_runs (workspace_id, started_at DESC);

CREATE TABLE search_test_run_results (
    run_id UUID NOT NULL REFERENCES search_test_runs(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    family TEXT NOT NULL,
    expected_path_contains TEXT NOT NULL,
    -- Rang du doc attendu dans les résultats (NULL = absent du top-k).
    rank INT,
    PRIMARY KEY (run_id, question)
);
