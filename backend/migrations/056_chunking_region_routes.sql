-- Migration 056 — routes de régions par stratégie de chunking (spec chunking §3)
--
-- Une route dirige les régions `(region_type, qualifier)` d'une stratégie vers
-- leur traitement : sous-stratégie du catalogue (`target_strategy_id`),
-- atomicité inline (`atomic`, target NULL), ou exclusion d'embedding
-- (`overflow_policy = 'parent_only'`). Résolution par spécificité décroissante
-- côté code : (type, qualifier) exact → (type, '*') → défaut inline.
--
-- FK plutôt que jsonb : ON DELETE CASCADE côté stratégie propriétaire,
-- ON DELETE RESTRICT côté cible (on ne supprime pas une stratégie référencée
-- par une route).

CREATE TABLE chunking_strategy_region_routes (
    strategy_id        UUID NOT NULL REFERENCES chunking_strategies(id) ON DELETE CASCADE,
    region_type        TEXT NOT NULL,
    qualifier          TEXT NOT NULL DEFAULT '*',
    target_strategy_id UUID REFERENCES chunking_strategies(id) ON DELETE RESTRICT,
    atomic             BOOL NOT NULL DEFAULT false,
    overflow_policy    TEXT NOT NULL DEFAULT 'keep_whole'
        CHECK (overflow_policy IN ('keep_whole', 'split_fallback', 'parent_only')),
    PRIMARY KEY (strategy_id, region_type, qualifier)
);
