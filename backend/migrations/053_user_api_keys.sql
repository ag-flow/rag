-- Migration 053 — clés API au niveau utilisateur (remplace les clés par workspace)
--
-- Nouveau modèle : une clé appartient à un utilisateur (owner_id = sha256(email)),
-- est montrée UNE SEULE FOIS à la création/rotation, et seule son empreinte
-- SHA-256 est stockée (pas de valeur chiffrée, pas de lien Harpocrate).
-- Les droits sont accordés par workspace via user_api_key_workspaces, avec
-- deux permissions : can_read (recherche MCP) et can_write (indexation push).
--
-- Rebuild de zéro (décision produit) : l'ancienne table workspace_api_keys est
-- supprimée sans reprise — les clés existantes cessent de fonctionner.

DROP TABLE IF EXISTS workspace_api_keys;

CREATE TABLE user_api_keys (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id     TEXT NOT NULL,
    name         TEXT NOT NULL,
    fingerprint  TEXT NOT NULL UNIQUE,
    revoked_at   TIMESTAMPTZ,
    rotated_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner_id, name)
);

CREATE INDEX user_api_keys_owner ON user_api_keys (owner_id);

CREATE TABLE user_api_key_workspaces (
    api_key_id   UUID NOT NULL REFERENCES user_api_keys(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    can_read     BOOLEAN NOT NULL DEFAULT true,
    can_write    BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (api_key_id, workspace_id)
);

CREATE INDEX user_api_key_workspaces_ws ON user_api_key_workspaces (workspace_id);
