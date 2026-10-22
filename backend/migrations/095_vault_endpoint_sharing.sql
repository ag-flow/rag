-- Migration 095 — partage des endpoints de coffre
--
-- Décision architecte (2026-10-18, epic f3cc98a8) : un endpoint, jusque-là
-- utilisable seulement par qui voit son coffre (coffre par défaut ou possédé),
-- peut être partagé :
--   - avec tout le monde (`shared_with_all`) ;
--   - sinon avec des utilisateurs existants, nommément (`vault_endpoint_shares`).
-- Le bénéficiaire UTILISE l'endpoint (création de workspace), il ne le modifie
-- pas : l'écriture reste réservée au propriétaire du coffre.
--
-- Bénéficiaire = `users.id` (cascade à la suppression du compte) ET son
-- `owner_id`, calculé côté Python par `principal_to_owner_id` au moment du
-- partage. Le recalculer en SQL (`sha256(lower(email))`) divergerait : le
-- lower() de Postgres ne replie pas l'Unicode comme celui de Python. Comme
-- dans toutes les tables qui portent un owner_id, un changement d'email
-- désynchronise la ligne — défaut transverse, traité par le chantier d'ancrage
-- d'identité, pas ici. ON DELETE CASCADE des deux côtés : jamais d'orphelin.

ALTER TABLE vault_endpoints
    ADD COLUMN shared_with_all BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE vault_endpoint_shares (
    endpoint_id UUID NOT NULL REFERENCES vault_endpoints(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    owner_id    TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (endpoint_id, user_id)
);

CREATE INDEX vault_endpoint_shares_user ON vault_endpoint_shares (user_id);
CREATE INDEX vault_endpoint_shares_owner ON vault_endpoint_shares (owner_id);
