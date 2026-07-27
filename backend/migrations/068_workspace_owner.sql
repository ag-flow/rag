-- Migration 068 — workspaces : rattachement à leur créateur.
--
-- Correction du modèle (2026-07-20) : un workspace appartient à l'utilisateur
-- qui l'a créé, EXACTEMENT comme les stratégies de chunking, les prompts et les
-- modèles (owner_id TEXT = sha256(email) ; NULL = partagé/système, visible par
-- tous). L'accès et l'attribution suivent la même règle de visibilité :
--     owner_id IS NULL (partagé)  OU  owner_id = <caller>
--
-- Backfill : les workspaces existants passent owner_id NULL (partagés) — aucune
-- perte d'accès. Les nouveaux workspaces sont attribués à leur créateur.

ALTER TABLE workspaces ADD COLUMN owner_id TEXT NULL;

CREATE INDEX idx_workspaces_owner ON workspaces (owner_id);

COMMENT ON COLUMN workspaces.owner_id IS
    'sha256(email) du créateur ; NULL = workspace partagé (visible par tous)';
