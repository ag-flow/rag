-- Migration 098 — demandes en cours du parcours « Connecter à Harpocrate »
--
-- Entre le départ vers Harpocrate et le retour du navigateur, ragflow doit
-- garder le `code_verifier` PKCE et la clé PRIVÉE éphémère (ConnectState du
-- SDK ≥ 0.8.0). Le contrat Harpocrate interdit de les confier au navigateur :
-- la session Starlette est un cookie signé mais LISIBLE, elle ne peut porter
-- que le jeton de liaison. L'état vit donc ici, chiffré comme les clés des
-- coffres (pgp_sym_encrypt + HARPOCRATE_DEK).
--
-- Une ligne par demande :
--   - state_hash : SHA-256 du `state` renvoyé par Harpocrate (jamais le state
--     en clair : la colonne sert de clé de recherche, pas de preuve) ;
--   - binding_hash : SHA-256 du jeton tiré au départ et gardé dans la session
--     de l'admin — un retour présenté par un autre navigateur ne correspond pas ;
--   - consumed_at : posé atomiquement au retour, un rejeu ne trouve plus rien ;
--   - expires_at : 15 min, la durée de vie d'une demande côté Harpocrate.
-- Le coffre à créer (nom, libellé, URL, défaut) est figé au départ : ce que
-- l'admin a saisi ne transite pas par Harpocrate.

CREATE TABLE harpocrate_connect_requests (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state_hash              TEXT NOT NULL UNIQUE,
    binding_hash            TEXT NOT NULL,
    owner_id                TEXT NOT NULL,
    vault_name              TEXT NOT NULL,
    vault_label             TEXT NOT NULL,
    base_url                TEXT NOT NULL,
    is_default              BOOLEAN NOT NULL,
    connect_state_encrypted BYTEA NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at              TIMESTAMPTZ NOT NULL,
    consumed_at             TIMESTAMPTZ
);

CREATE INDEX harpocrate_connect_requests_expires
    ON harpocrate_connect_requests (expires_at);
