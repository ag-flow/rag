-- Migration 090 — endpoint de fallback + paramètres du circuit breaker
--
-- Un endpoint peut déclarer UN endpoint de fallback (même coffre, un seul
-- niveau — gardes applicatives dans services/endpoint_fallback.py). La
-- substitution au runtime est granulaire par service (lot 2). Les paramètres
-- du breaker vivent au niveau de l'endpoint (enabler docflow f94bfd84).

ALTER TABLE vault_endpoints
    ADD COLUMN fallback_endpoint_id UUID REFERENCES vault_endpoints(id) ON DELETE SET NULL,
    ADD COLUMN failure_threshold INT NOT NULL DEFAULT 3,
    ADD COLUMN cooldown_seconds INT NOT NULL DEFAULT 60;

ALTER TABLE vault_endpoints
    ADD CONSTRAINT vault_endpoints_fallback_not_self
    CHECK (fallback_endpoint_id IS NULL OR fallback_endpoint_id <> id);

ALTER TABLE vault_endpoints
    ADD CONSTRAINT vault_endpoints_breaker_params_positive
    CHECK (failure_threshold >= 1 AND cooldown_seconds >= 1);
