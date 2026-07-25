-- Migration 075 — paramètres de la demande sur index_jobs (drill-down IHM)
--
-- Les paramètres d'un push (title, strategy, force, source_url, taille du
-- contenu) vivent dans push_job_payloads, PURGÉ après traitement : invisibles
-- pour un job terminé. On fige un instantané des paramètres de la demande sur
-- le job à l'enfilage (NULL pour les jobs git/admin, qui n'en ont pas).

ALTER TABLE index_jobs ADD COLUMN params JSONB;
