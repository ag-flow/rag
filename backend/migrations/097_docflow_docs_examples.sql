-- Migration 097 — exemples système pour une documentation docflow
--
-- Livrés à toute installation (nouvelle ou existante) comme modèles à
-- dupliquer : système = owner_id NULL, visibles de tous, non éditables.
-- ON CONFLICT DO NOTHING : une installation qui porte déjà un objet système
-- de même slug / même (langue, clé) garde le sien.
--
-- 1) Stratégie `docflow-docs` (prose) : réglages éprouvés sur les pages docflow.
--    - heading_levels 1,2,3 : les pages docflow structurent jusqu'au H3, un
--      découpage à H2 seulement produit des sections parentes trop longues ;
--    - floor_tokens 32 (au lieu de 64) : garde les sections courtes (FAQ,
--      définitions) au lieu de les fusionner avec la voisine ;
--    - aucun nettoyage : le markdown docflow est déjà propre, retirer HTML ou
--      séparateurs casserait les composants df-* et les tableaux.
-- 2) Prompt `docflow-docs-contexte-chunk` (mode Chunk) : une phrase de
--    contexte préfixée à chaque chunk. Il contient {chunk} : sans ce
--    placeholder le LLM ne reçoit jamais le fragment (seulement la page en
--    préfixe) et produit le même contexte pour tous les chunks.
-- Le prompt n'est PAS lié à la stratégie : un contexte inline coûte un appel
-- LLM par chunk, il ne doit jamais s'activer en choisissant une stratégie.

INSERT INTO chunking_strategies (owner_id, workspace_id, label, slug, algo, params)
VALUES (
    NULL, NULL, 'docflow-docs', 'docflow-docs', 'prose',
    '{"child_target_tokens":384,"floor_tokens":32,"overlap_tokens":64,"breadcrumb_depth":-1,"heading_levels":[1,2,3]}'::jsonb
)
ON CONFLICT DO NOTHING;

INSERT INTO prompt_templates
    (owner_id, name, language, description, metadata_key, result_type,
     target, timing, prompt)
VALUES (
    NULL,
    'docflow-docs-contexte-chunk',
    'fr-FR',
    'Contexte d''embedding pour les pages de documentation docflow (guides, '
    'cadrages). Préfixe chaque chunk d''une phrase de situation pour améliorer '
    'le rappel sémantique hors contexte de page.',
    'context',
    'text',
    'chunk',
    'embedding_inline',
    'Tu enrichis un fragment (chunk) issu d''une page de documentation technique en français
(guides, cadrages, spécifications) avant sa vectorisation. Objectif : rendre le fragment
retrouvable même isolé de sa page. La page complète t''a été fournie ci-dessus.

À partir de la page et du fragment ci-dessous (précédé de son fil d''Ariane), produis UNE
seule phrase de contexte, factuelle et sobre, qui situe :
- le sujet de la page dont provient le fragment ;
- la section ou le thème précis que le fragment traite.

Règles strictes :
- Ne reformule pas et n''interprète pas le contenu ; contente-toi de le situer.
- N''invente aucun fait absent de la page ou du fragment.
- Reste sous 25 mots, en français, sans préambule ni guillemets.
- Si le fragment est déjà auto-suffisant (titre explicite), renvoie une phrase minimale
  plutôt que du remplissage.

<fragment>
{chunk}
</fragment>

Réponds uniquement par la phrase de contexte.'
)
ON CONFLICT DO NOTHING;
