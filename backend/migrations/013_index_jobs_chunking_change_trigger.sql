-- Migration 013 — élargit le CHECK index_jobs.triggered_by avec 'reindex_chunking_change'
--
-- Symétrique à 007 (qui a ajouté 'reindex_indexer_change' lors de M5).
-- Permet aux jobs créés par apply_chunking_change(confirm=true) de s'insérer
-- avec un trigger discriminant des autres reindex (manual, indexer_change…).
--
-- Cf. design M9 §4.6 et §5.2 — flow PUT /chunking-config?confirm=true.

ALTER TABLE index_jobs DROP CONSTRAINT index_jobs_triggered_by_check;

ALTER TABLE index_jobs ADD CONSTRAINT index_jobs_triggered_by_check
    CHECK (triggered_by IN (
        'webhook',
        'manual',
        'push',
        'schedule',
        'reindex_indexer_change',
        'reindex_chunking_change'
    ));
