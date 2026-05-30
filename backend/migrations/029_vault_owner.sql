-- Migration 029 — ownership des coffres Harpocrate

ALTER TABLE harpocrate_vaults ADD COLUMN owner_id TEXT NOT NULL DEFAULT '';
CREATE INDEX harpocrate_vaults_owner ON harpocrate_vaults (owner_id);
