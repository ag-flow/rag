-- Migration 070 — ré-évaluation d'UN document poussé (API par clé)
--
-- Un push est dédup-gardé par (content_hash, indexer_used) : repousser le même
-- contenu après un changement de stratégie/moteur est classé 'skipped'. La
-- ré-évaluation force le re-traitement d'un document dont l'appelant renvoie le
-- contenu (aucun stockage source : les chunks servent à la consultation/debug).
--
-- 1) `force` sur le payload : bypass explicite du dedup, porté par le job.
-- 2) `triggered_by='reindex_document'` : trace distincte dans les listes de jobs
--    (même machinerie que push, routée vers le même exécuteur).

ALTER TABLE push_job_payloads
    ADD COLUMN force BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE index_jobs DROP CONSTRAINT index_jobs_triggered_by_check;
ALTER TABLE index_jobs ADD CONSTRAINT index_jobs_triggered_by_check
    CHECK (triggered_by IN (
        'webhook', 'manual', 'push', 'schedule',
        'reindex_indexer_change', 'reindex_chunking_change', 'reindex_document',
        'delete', 'rebuild_lexical_index'
    ));
