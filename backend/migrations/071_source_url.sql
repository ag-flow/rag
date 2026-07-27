-- Migration 071 — URL de consultation de l'original (sans stockage du contenu)
--
-- Le caller fournit au push une URL auto-authentifiante pointant vers le
-- document original ; on ne persiste QUE la référence (pas le contenu). L'IHM et
-- les API de lecture y renvoient pour consulter l'exact.
--
-- 1) `source_url` sur le payload : portée par le job jusqu'à l'indexation.
-- 2) `source_url` sur indexed_documents : état courant par document (last non-null
--    gagne, cf. COALESCE côté indexeur — un re-index git/enrichissement sans URL
--    ne doit pas effacer celle fournie au push).

ALTER TABLE push_job_payloads ADD COLUMN source_url TEXT;
ALTER TABLE indexed_documents ADD COLUMN source_url TEXT;
