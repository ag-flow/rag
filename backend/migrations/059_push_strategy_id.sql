-- Migration 059 — mode service : binding du push par strategy_id (spec chunking §5, F4)
--
-- Le slug de stratégie transmis au push (mode service, caller authentifié par
-- clé API user) est résolu À L'ACCEPTATION dans la bibliothèque du caller
-- (puis stratégies système) ; le payload du job ne porte plus que l'id lié.
-- Le worker (mode job) reste ainsi strictement sans contexte utilisateur —
-- règle d'or : binding par id.
--
-- Pas de FK sur strategy_id : les payloads sont transients et une FK RESTRICT
-- bloquerait la suppression de stratégies à cause de payloads déjà traités.
-- Si l'id lié a disparu à l'exécution (cas résiduel), le job échoue avec une
-- erreur typée (StrategyBindingLostError) — jamais de repli silencieux sur le
-- routage par extension.

ALTER TABLE push_job_payloads DROP COLUMN strategy_override;
ALTER TABLE push_job_payloads ADD COLUMN strategy_id UUID;
