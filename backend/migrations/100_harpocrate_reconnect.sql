-- Migration 100 — « Reconnecter » un coffre existant à Harpocrate
--
-- Le parcours de reconnexion réutilise la table des demandes de 098 et la MÊME
-- URL de retour : celle-ci est déclarée chez Harpocrate au caractère près, une
-- seconde URL obligerait chaque admin Harpocrate à redéclarer ragflow.
--
--   - vault_id : coffre dont la clé sera remplacée ; NULL = création (098).
--     ON DELETE CASCADE : un coffre supprimé entre le départ et le retour
--     emporte sa demande, le retour ne trouve alors plus rien.
--
-- Si Harpocrate rend une clé sur un AUTRE wallet que la clé actuelle (ou si la
-- clé actuelle ne permet plus de le vérifier), les références de secrets
-- existantes pointeraient ailleurs : ragflow tient la nouvelle clé en attente
-- de la confirmation de l'admin au lieu de l'enregistrer.
--   - pending_key_encrypted : api_key_id + token obtenus, chiffrés comme les
--     clés des coffres (pgp_sym_encrypt + HARPOCRATE_DEK), effacés dès la
--     décision ; la purge des demandes expirées les emporte sinon ;
--   - previous_wallet_id / pending_wallet_id : de quoi montrer l'écart ;
--     previous_wallet_id NULL = clé actuelle muette (expirée, révoquée) ;
--   - confirm_binding_hash : SHA-256 d'un second jeton de liaison, posé dans
--     la session au retour — seule cette session peut confirmer ;
--   - resolved_at : décision prise (confirmée ou refusée), rejeu impossible.

ALTER TABLE harpocrate_connect_requests
    ADD COLUMN vault_id UUID REFERENCES harpocrate_vaults (id) ON DELETE CASCADE,
    ADD COLUMN pending_key_encrypted BYTEA,
    ADD COLUMN previous_wallet_id UUID,
    ADD COLUMN pending_wallet_id UUID,
    ADD COLUMN confirm_binding_hash TEXT,
    ADD COLUMN resolved_at TIMESTAMPTZ;
