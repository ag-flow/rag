-- Migration 065 — moteur de chunking par défaut : structured
--
-- L'epic « Qualité du retrieval » (F1→F6, S5.3) fait du pipeline structured
-- (stratégies possédées, binding par id, régions, tokens) le monde de
-- référence. Les NOUVEAUX workspaces démarrent désormais dessus ; les
-- workspaces existants conservent leur valeur (la bascule reste pilotée par
-- PUT /chunking-config/engine avec sa garde de réindexation).

ALTER TABLE chunking_configs ALTER COLUMN engine SET DEFAULT 'structured';
