-- Migration 094 — clés API : exiger une identité humaine signée (OBO)
--
-- Décision architecte (2026-10-18, epic f3cc98a8) : le propriétaire d'une clé
-- peut exiger que chaque appel porte une identité OBO valide (contrat d0e2dad3
-- v6). Sans le flag, l'OBO reste optionnel (repli sur l'owner de la clé) ;
-- avec, son absence ou son échec est un 401 — fail closed.
--
-- Limite assumée : la signature OBO utilise la clé elle-même — le flag impose
-- l'attribution à un humain connu, il ne protège pas une clé volée.
--
-- DEFAULT false : les clés existantes gardent exactement leur comportement.

ALTER TABLE user_api_keys
    ADD COLUMN require_obo BOOLEAN NOT NULL DEFAULT false;
