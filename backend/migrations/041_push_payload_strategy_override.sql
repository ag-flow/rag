-- Migration 041 — override de stratégie de chunking sur le push ad hoc
--
-- ADR 0001 §2 : l'ajout ad hoc via POST /workspaces/{name}/index peut forcer
-- une stratégie nommée (prime sur le routage par type). On persiste l'override
-- avec le payload pour le rejouer dans le worker. NULL = pas d'override.

ALTER TABLE push_job_payloads ADD COLUMN strategy_override TEXT;
