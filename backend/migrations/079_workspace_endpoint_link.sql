-- Migration 079 — lien workspace → endpoint d'origine
--
-- La config d'un workspace est un SNAPSHOT de l'endpoint choisi à la création.
-- Pour permettre « Rafraîchir depuis l'endpoint » (recopier indexer/rerank/llm
-- depuis le MÊME endpoint, sans en changer), on mémorise le lien. NULL pour les
-- workspaces créés avant cette migration (bouton inactif — recréer le workspace).

ALTER TABLE workspaces
    ADD COLUMN endpoint_id UUID REFERENCES vault_endpoints(id) ON DELETE SET NULL;
