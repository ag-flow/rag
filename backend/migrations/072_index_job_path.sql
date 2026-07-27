-- Migration 072 — path du document sur index_jobs (visibilité IHM des jobs)
--
-- Les jobs mono-document (push / reindex_document / delete) concernent UN path.
-- Il vit dans push_job_payloads / delete_job_payloads, mais ces payloads sont
-- SUPPRIMÉS après traitement (cf. executor) — donc invisibles pour un job done.
-- On copie le path sur le job lui-même (NULL pour les jobs git multi-fichiers,
-- dont les fichiers restent dans index_job_files).

ALTER TABLE index_jobs ADD COLUMN path TEXT;
