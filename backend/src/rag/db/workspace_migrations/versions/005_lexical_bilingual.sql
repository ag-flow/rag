-- Workspace migration 005 — index lexical bilingue pondéré (D4, SR2.1)
--
-- Remplace la représentation `simple` seule (003) par la DOUBLE
-- représentation pondérée dans un seul tsvector :
--   - poids A : canal `simple` + unaccent → match EXACT (identifiants
--     techniques, codes, termes anglais, saisie sans accents) ;
--   - poids B : canal `french` + unaccent → rapprochement morphologique de
--     la prose. L'unaccent est appliqué AVANT le stemming : le snowball
--     français stemme mal les mots désaccentués (« strategie » ↛ « stratég »),
--     donc les deux côtés (index et requête) désaccentuent d'abord pour que
--     « strategie » et « stratégies » convergent vers la même racine.
-- ts_rank (poids par défaut A=1.0 > B=0.4) fait dominer le match exact sur
-- le match par racine — hiérarchie voulue par D4.
--
-- `unaccent()` est STABLE (dépend d'un dictionnaire) : une colonne générée
-- exige de l'IMMUTABLE → wrapper `immutable_unaccent` figé sur le
-- dictionnaire public.unaccent (pratique standard ; le dictionnaire ne
-- change pas sur nos instances).
--
-- Ajout purement additif côté vecteurs : la colonne est régénérée par
-- Postgres au ADD (c'est le backfill), AUCUNE réindexation vectorielle.

CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE OR REPLACE FUNCTION immutable_unaccent(text) RETURNS text AS
$$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$
LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT;

DROP INDEX IF EXISTS embeddings_content_tsv;
ALTER TABLE embeddings DROP COLUMN IF EXISTS content_tsv;
ALTER TABLE embeddings
    ADD COLUMN content_tsv tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', immutable_unaccent(content)), 'A') ||
        setweight(to_tsvector('french', immutable_unaccent(content)), 'B')
    ) STORED;

CREATE INDEX embeddings_content_tsv ON embeddings USING GIN (content_tsv);
