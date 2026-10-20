-- Migration 099 — ancrage de l'identité sur (issuer, sub), propriétaire figé,
-- rôle en base (ticket 730cb2d6, STANDARD Authentification OIDC §1, §3, §4, §9).
--
-- 1) owner_id FIGÉ par utilisateur. Jusqu'ici le propriétaire des objets
--    (coffres, workspaces, stratégies, prompts, clés) était recalculé à chaque
--    requête depuis l'email de la session : un changement d'email — côté IdP,
--    dans le profil, ou de règle de dérivation — rendait tous les objets
--    orphelins (incident `vault1` du 2026-10-20). Il est désormais posé UNE
--    fois, à la création de la ligne, et ne bouge plus.
--    Backfill = sha256(lower(email)), exactement la valeur que la dérivation
--    actuelle produit : aucun objet existant ne change de propriétaire.
-- 2) (oidc_issuer, oidc_sub) : l'ancrage définitif d'un compte fédéré, unique.
--    NULL tant que le compte ne s'est jamais connecté en OIDC (épinglé alors).
-- 3) role : l'application autorise, l'IdP authentifie. NULL = rôle encore
--    inconnu (ligne créée par le profil d'un utilisateur OIDC avant ce lot) :
--    fixé au prochain login à partir de la suggestion du token, puis la base
--    fait foi. Les comptes locaux existants sont admin (c'était déjà la règle :
--    toute session locale valide est admin).
-- 4) Historique des épinglages : sans lui, une bascule d'émetteur est
--    irréversible et non auditable.

ALTER TABLE users
    ADD COLUMN oidc_issuer TEXT,
    ADD COLUMN oidc_sub    TEXT,
    ADD COLUMN owner_id    TEXT,
    ADD COLUMN role        TEXT CHECK (role IN ('rag-admin', 'rag-viewer'));

UPDATE users SET owner_id = encode(digest(lower(email), 'sha256'), 'hex');
UPDATE users SET role = 'rag-admin' WHERE password_hash <> '';

ALTER TABLE users ALTER COLUMN owner_id SET NOT NULL;
-- Index simple, pas unique : deux lignes dont l'email ne diffère que par la
-- casse donneraient le même owner_id, et une contrainte unique ferait échouer
-- la migration — donc le démarrage — sur une base existante.
CREATE INDEX users_owner_id ON users (owner_id);
-- Le sub n'a de sens que qualifié par son émetteur : jamais l'un sans l'autre.
ALTER TABLE users ADD CONSTRAINT users_oidc_anchor_pair
    CHECK ((oidc_issuer IS NULL) = (oidc_sub IS NULL));
CREATE UNIQUE INDEX users_oidc_anchor_unique ON users (oidc_issuer, oidc_sub)
    WHERE oidc_issuer IS NOT NULL;

-- Un seul point de calcul du propriétaire, quel que soit le chemin de création
-- (bootstrap, compte local, provisioning OIDC) : un INSERT qui l'oublie ne
-- peut pas créer de ligne sans propriétaire. Jamais recalculé ensuite.
CREATE FUNCTION users_freeze_owner_id() RETURNS trigger AS $$
BEGIN
    IF NEW.owner_id IS NULL THEN
        NEW.owner_id := encode(digest(lower(NEW.email), 'sha256'), 'hex');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_owner_id_on_insert
    BEFORE INSERT ON users
    FOR EACH ROW EXECUTE FUNCTION users_freeze_owner_id();

CREATE TABLE user_oidc_identity_history (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    oidc_issuer TEXT NOT NULL,
    oidc_sub    TEXT NOT NULL,
    pinned_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Posé quand un nouvel émetteur remplace celui-ci (re-liaison).
    replaced_at TIMESTAMPTZ
);
CREATE INDEX user_oidc_identity_history_user ON user_oidc_identity_history (user_id);
