-- Workspace migration 003 — recherche hybride : colonne tsvector générée + index GIN
--
-- Ajoute sur `embeddings` une colonne `content_tsv` auto-maintenue (GENERATED ALWAYS AS STORED).
-- La config `simple` : pas de stemming, pas de stopwords → les identifiants de code sont
-- préservés entiers (`RAG_MASTER_KEY` reste un lexème unique).
-- Backfill automatique des lignes existantes (STORED = calculé à l'INSERT de la colonne).
-- Legacy (chunk_hash NULL) indexé aussi → l'hybride profite aux corpus anciens sans reindexation.

ALTER TABLE embeddings
    ADD COLUMN content_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED;

CREATE INDEX embeddings_content_tsv ON embeddings USING GIN (content_tsv);
