-- Workspace migration 004 — ordre déclaré des sections parentes
--
-- section_index : position de la section dans le document (0-based), déclarée au chunking.
-- Nécessaire pour get_document (M18) et chunk-viz (M15) : ORDER BY section_index garantit
-- l'ordre du doc original indépendamment de l'id (ON CONFLICT DO UPDATE ne change pas l'id).
--
-- Backfill : ORDER BY id ≈ ordre d'insertion = meilleure approximation pour les sections
-- existantes. Les nouvelles indexations renseignent section_index natif.

ALTER TABLE sections
    ADD COLUMN section_index INT;

WITH ranked AS (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY path ORDER BY id) - 1 AS idx
    FROM sections
)
UPDATE sections
SET section_index = ranked.idx
FROM ranked
WHERE sections.id = ranked.id;
