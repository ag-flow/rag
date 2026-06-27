-- Workspace migration 002 — small-to-big + hash par chunk (ADR 0001 §3/§5)
--
-- Ajoute la table parente `sections` (texte renvoyé au LLM) et, sur
-- `embeddings`, le lien `section_id` + le `chunk_hash` (identité stable du
-- chunk normalisé). On remplace l'unicité (path, chunk_index) par une unicité
-- partielle (path, chunk_hash) : chunk_index n'est plus qu'un ordre de
-- présentation (le diff incrémental réutilise les chunks par hash).
--
-- Compatibilité legacy : les lignes existantes ont chunk_hash NULL ; l'index
-- partiel ne les contraint pas, et le pipeline legacy (DELETE WHERE path +
-- INSERT) continue de fonctionner inchangé.

CREATE TABLE sections (
    id          BIGSERIAL PRIMARY KEY,
    path        TEXT NOT NULL,
    section_key TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    indexed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (path, section_key)
);

ALTER TABLE embeddings
    ADD COLUMN section_id BIGINT REFERENCES sections(id) ON DELETE CASCADE,
    ADD COLUMN chunk_hash TEXT;

-- chunk_index n'est plus une identité → on lève son unicité.
ALTER TABLE embeddings DROP CONSTRAINT embeddings_path_chunk_index_key;

-- Identité d'un chunk structuré : (path, chunk_hash). Partiel pour ne pas
-- contraindre les lignes legacy (chunk_hash NULL).
CREATE UNIQUE INDEX embeddings_path_chunk_hash
    ON embeddings (path, chunk_hash) WHERE chunk_hash IS NOT NULL;

CREATE INDEX embeddings_section_id ON embeddings (section_id);
CREATE INDEX sections_path ON sections (path);
