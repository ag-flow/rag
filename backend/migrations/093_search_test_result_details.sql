-- Migration 093 — banc de test : détail analysable par question
--
-- Demande architecte 2026-07-28 : chaque résultat de campagne doit permettre
-- de comprendre CE QUI ÉTAIT ATTENDU et CE QUI EST REVENU — assez
-- d'information pour qu'un agent (ou l'IHM) analyse un échec sans rejouer la
-- recherche.

ALTER TABLE search_test_run_results
    -- Top-k retourné par le moteur au moment du run, ordonné :
    -- [{rank, path, score, chunk_index, snippet, matched}].
    ADD COLUMN returned JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Erreur d'exécution de la recherche pour CETTE question (NULL = appel OK ;
    -- distinct d'un rank NULL qui signifie « document attendu absent »).
    ADD COLUMN error TEXT;
