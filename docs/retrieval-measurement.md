# Protocole de mesure du retrieval — où activer le contextual retrieval

Le contexte LLM par chunk/région (« Prompt B », migration 061) coûte un appel
LLM par chunk à la première indexation. Il ne s'active **jamais par défaut** :
on ne le paie que là où le retrieval mesuré patine. Ce protocole décide où.

## 1. Constituer un golden set

Par workspace candidat : 20 à 50 questions réelles (tickets, questions Slack,
requêtes MCP observées dans les logs `mcp.search`), chacune annotée avec le ou
les `path` attendus dans les résultats. Stocker le set dans le repo du corpus
(`golden/queries.yaml`) — il doit évoluer avec le corpus.

## 2. Mesurer la base

Outillé par `scripts/retrieval_bench.py` :

```bash
uv run --project backend python scripts/retrieval_bench.py \
    --base-url http://192.168.10.184 --workspace docflow \
    --golden golden/docflow.yaml --api-key <clé user can_read>
```

- **hit@5** : proportion de questions dont un path attendu est dans le top 5 ;
- **MRR@10** : moyenne de `1/rang` du premier path attendu (match sur `path`
  ou `source_path`).

Trois passes (le reranking peut varier), moyenne. C'est la référence.
Format du golden set : `golden/queries.example.yaml`.

## 3. Activer de façon ciblée

Activer le contexte inline UNIQUEMENT sur le segment qui échoue :

- échecs concentrés sur une extension → template `chunk`/`embedding_inline`
  lié au trigger de cette extension ;
- échecs sur des documents à diagrammes → route `parent_only` sur
  `code_fence:mermaid` + template `region:code_fence:mermaid`.

Réindexer le workspace (la première passe paie la génération ; les
réindexations suivantes lisent le cache `chunk_context_cache`).

## 4. Re-mesurer et décider

Même mesure, même golden set. Garder l'activation si **hit@5 gagne ≥ 5 points
ou MRR ≥ 0,05** ; sinon désactiver le binding (le cache reste, réactivable
sans coût). Journaliser la décision dans la fiche du workspace.

## Coûts (repères, doc Anthropic 2026-07)

Prompt caching : préfixe document marqué `cache_control` (TTL 5 min, rafale
par document) — écriture +25 %, lecture −90 %. Un document de 20 chunks coûte
~1 lecture complète + 20 sorties ≤ 120 tokens. La régénération n'a lieu que si
le chunk source ou `prompt_version` change.
