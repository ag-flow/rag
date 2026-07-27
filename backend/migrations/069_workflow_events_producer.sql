-- Migration 069 — producteur d'events vers ag.flow workflow (Porte A).
--
-- Émission robuste : le code métier n'appelle JAMAIS le réseau. Il enfile
-- l'enveloppe (octets exacts à signer/poster) dans un OUTBOX transactionnel ;
-- un worker de fond signe et POST hors transaction, avec retry/backoff.
-- Réf : globals « Émettre des events vers ag.flow workflow » + guide producteur.

-- Outbox : une ligne = une enveloppe prête à signer/poster.
CREATE TABLE workflow_event_outbox (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_code      TEXT NOT NULL,
    payload         BYTEA NOT NULL,            -- octets EXACTS à signer ET poster
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'delivered', 'failed')),
    attempts        INT  NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at    TIMESTAMPTZ
);

-- Sélection des lignes dues par le worker (pending, échéance atteinte).
CREATE INDEX workflow_event_outbox_due
    ON workflow_event_outbox (next_attempt_at)
    WHERE status = 'pending';

-- Config singleton du relais (éditée en admin, effet à chaud).
CREATE TABLE events_producer_config (
    id                INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    enabled           BOOLEAN NOT NULL DEFAULT false,
    workflow_base_url TEXT NOT NULL DEFAULT '',
    source_id         TEXT NOT NULL DEFAULT '',   -- GUID attribué par workflow
    secret_ref        TEXT NOT NULL DEFAULT '',   -- ref vault de la clé HMAC partagée
    source_uri        TEXT NOT NULL DEFAULT 'urn:yoops:rag',
    events            TEXT[] NOT NULL DEFAULT '{}',  -- liste blanche (vide = aucun relais)
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO events_producer_config (id) VALUES (1) ON CONFLICT DO NOTHING;
