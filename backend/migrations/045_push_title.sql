-- Migration 045 — champ title optionnel sur l'indexation externe

ALTER TABLE push_job_payloads ADD COLUMN title TEXT;

ALTER TABLE indexed_documents ADD COLUMN title TEXT;
