-- Migration 063 — config de recherche par workspace (D5, D6 — R3/R4)
--
-- 1. `fts_config` disparaît : la représentation lexicale est désormais LE
--    montage bilingue pondéré de D4 (workspace migration 005), identique
--    partout — plus de configuration de dictionnaire par workspace.
-- 2. Pondération des canaux (D6) : deux curseurs exposés dans l'onglet
--    Recherche, défaut 50/50. Fusion par rangs : score = Σ wᵢ/(k + rangᵢ).
-- 3. Moteur lexical au choix (D5) : `fts` (natif, défaut) ou `bm25`
--    (extension, activable si disponible sur l'instance). La bascule
--    reconstruit l'index lexical (job `rebuild_lexical_index`), jamais les
--    vecteurs.

ALTER TABLE hybrid_configs
    DROP COLUMN fts_config,
    ADD COLUMN weight_lexical REAL NOT NULL DEFAULT 0.5
        CHECK (weight_lexical >= 0 AND weight_lexical <= 1),
    ADD COLUMN weight_vector REAL NOT NULL DEFAULT 0.5
        CHECK (weight_vector >= 0 AND weight_vector <= 1),
    ADD COLUMN lexical_engine TEXT NOT NULL DEFAULT 'fts'
        CHECK (lexical_engine IN ('fts', 'bm25'));

-- Nouveau type de job : reconstruction de l'index lexical à la bascule de
-- moteur (D5). Même machinerie que les réindexations existantes.
ALTER TABLE index_jobs DROP CONSTRAINT index_jobs_triggered_by_check;
ALTER TABLE index_jobs ADD CONSTRAINT index_jobs_triggered_by_check
    CHECK (triggered_by IN (
        'webhook', 'manual', 'push', 'schedule',
        'reindex_indexer_change', 'reindex_chunking_change',
        'delete', 'rebuild_lexical_index'
    ));
