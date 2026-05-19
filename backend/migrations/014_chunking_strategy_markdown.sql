-- Migration 014 — chunking_configs.strategy : ajout de 'markdown'
--
-- Symétrique à 013 (widening de CHECK constraint).
-- Permet à la stratégie 'markdown' (M9c) d'être stockée. Les extras pour
-- markdown sont validés au niveau Pydantic ({heading_levels: int[]}), pas SQL.

ALTER TABLE chunking_configs DROP CONSTRAINT chunking_configs_strategy_check;
ALTER TABLE chunking_configs ADD CONSTRAINT chunking_configs_strategy_check
    CHECK (strategy IN ('paragraph', 'markdown'));
