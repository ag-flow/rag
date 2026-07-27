-- Migration 067 — clés API : modèle d'accès par NIVEAU (remplace les grants
-- par workspace).
--
-- Décision architecte (2026-07-20) : une clé n'a plus de droits fins par
-- workspace mais un niveau unique, appliqué à TOUS les workspaces de
-- l'instance (les workspaces n'ont pas de propriétaire) :
--   - read       : recherche / lecture MCP ;
--   - read_write : + indexation / push ;
--   - admin      : + ressources HORS workspace (bibliothèque : stratégies,
--                  prompts, modèles), isolées par owner_id de la clé.
-- La clé reste rattachée à son créateur (owner_id) — l'admin d'une clé ne
-- voit que SA bibliothèque.
--
-- Backfill : une clé qui avait au moins un grant can_write devient read_write,
-- sinon read. Puis la table de grants disparaît.

ALTER TABLE user_api_keys
    ADD COLUMN scope TEXT NOT NULL DEFAULT 'read'
        CHECK (scope IN ('read', 'read_write', 'admin'));

UPDATE user_api_keys k SET scope = 'read_write'
WHERE EXISTS (
    SELECT 1 FROM user_api_key_workspaces g
    WHERE g.api_key_id = k.id AND g.can_write
);

DROP TABLE user_api_key_workspaces;
