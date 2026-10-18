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
-- Bénéficiaire = `users.id` et non un owner_id figé : l'owner_id se dérive de
-- l'email courant, une ligne de partage suit donc l'utilisateur si son email
-- change. ON DELETE CASCADE des deux côtés : supprimer l'endpoint ou le compte
-- retire le partage, jamais de ligne orpheline.

ALTER TABLE vault_endpoints
    ADD COLUMN shared_with_all BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE vault_endpoint_shares (
    endpoint_id UUID NOT NULL REFERENCES vault_endpoints(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (endpoint_id, user_id)
);

CREATE INDEX vault_endpoint_shares_user ON vault_endpoint_shares (user_id);
