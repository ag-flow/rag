# Registre des bugs — admin-rag

Audit complet de l'application (backend, frontend, infra) mené le **2026-07-03**. Chaque bug est documenté dans une fiche `BUG-NNN-*.md` : sévérité, complexité, fichiers concernés, scénario de défaillance concret, code fautif, piste de correction, et **modèle Claude recommandé** pour la correction.

## Organisation des fichiers

- `Bugs/BUG-NNN-*.md` — bugs encore ouverts (`🔴 à corriger`).
- `Bugs/fixed/BUG-NNN-*.md` — bugs déjà corrigés et fusionnés dans `dev` (`🟢 corrigé`).

## Convention modèle de correction

| Modèle | Quand |
|--------|-------|
| **Sonnet** (`claude-sonnet-5`) | Correctif localisé, une décision simple à trancher, mécanique |
| **Opus** (`claude-opus-4-8`) | Multi-fichiers, logique subtile, concurrence, sécurité, décision de design |

## Statut

Chaque fiche porte un champ `**Statut**` en tête. Une fois corrigée, la fiche est marquée `🟢 corrigé` et déplacée dans `Bugs/fixed/`.

## Récapitulatif

- **Total : 97 bugs** — 68 recommandés Sonnet, 29 recommandés Opus
- **68/68 bugs Sonnet corrigés** (2026-07-04) — voir `Bugs/fixed/`
- **29 bugs Opus encore ouverts** — voir la liste ci-dessous
- Critiques : 4 (BUG-020, BUG-049, BUG-050, BUG-084)

## Index

| ID | Sév. | Modèle | Sujet |
|----|------|--------|-------|
| BUG-001 | haute | Sonnet | Provider rerank "openai" accepté par le schéma mais absent de la factory |
| BUG-002 | haute | Opus | Exceptions des providers rerank (429/timeout/auth) jamais capturées |
| BUG-003 | moyenne | Sonnet | Validation rerank différée : provider invalide = workspace semi-créé |
| BUG-004 | moyenne | Sonnet | Indices reranker appliqués sans validation de bornes ni unicité |
| BUG-005 | moyenne | Sonnet | Provider Ollama : résultats tronqués sans tri par score |
| BUG-006 | moyenne | Opus | Endpoint `/api/rerank` inexistant dans Ollama upstream |
| BUG-007 | basse | Sonnet | Échec lifespan au démarrage : fuite des pools Postgres |
| BUG-008 | moyenne | Sonnet | `run_backfill` : paramètre `workspace_dsn_map` ignoré |
| BUG-009 | moyenne | Sonnet | `SourceUpdateRequest` sans validateur `config.url` : PATCH efface l'URL git |
| BUG-010 | basse | Sonnet | `sync_worker_poll_interval_seconds` sans borne basse : busy loop |
| BUG-011 | basse | Sonnet | `base_url` rerank ignorée (cohere/voyage/jina) ou mal utilisée (dashscope) |
| BUG-012 | basse | Opus | `SearchHit.score` conserve le score pré-rerank après reranking |
| BUG-013 | haute | Sonnet | Enable/disable webhook invalide une query key inexistante |
| BUG-014 | moyenne | Sonnet | `rotateApiKey` appelle un endpoint backend inexistant |
| BUG-015 | moyenne | Sonnet | `getIndexKeyDetail` n'encode pas le path du document |
| BUG-016 | moyenne | Sonnet | `useJobLogs` ne gère jamais la fermeture WebSocket : statut bloqué |
| BUG-017 | moyenne | Opus | Expiration de session 401 non gérée, sans redirection |
| BUG-018 | basse | Sonnet | `useLastTestResult` lit le cache React Query non réactivement |
| BUG-019 | basse | Sonnet | `request()` caste un body 2xx non-JSON en `T` |
| BUG-020 | **critique** | Sonnet | Auth push/delete interroge colonnes supprimées (migration 033) : 500 |
| BUG-021 | haute | Sonnet | `except VaultUnreachable` mort : panne Harpocrate → 500 au lieu de 503 |
| BUG-022 | haute | Sonnet | `/mcp` legacy double-wrappe les refs vault complètes → 500 |
| BUG-023 | haute | Sonnet | `SecretResolver` fait du HTTP synchrone bloquant sur l'event loop |
| BUG-024 | moyenne | Opus | mcp_standard/playground droppent les refs de clé logique → embedding non auth |
| BUG-025 | moyenne | Sonnet | `GET /apikey` renvoie la clé en fin de rotation |
| BUG-026 | moyenne | Sonnet | Empoisonnement `ApiKeyCache` : 401 permanent jusqu'au restart |
| BUG-027 | moyenne | Opus | Contournement ACL owner des vaults via les sous-routers |
| BUG-028 | moyenne | Opus | `init-admin` : race count-then-insert (2e admin) ; bcrypt bloquant |
| BUG-029 | moyenne | Sonnet | `_clients_by_name` périmé quand la table vault se vide |
| BUG-030 | moyenne | Opus | Création de clé non transactionnelle : lignes `'pending'` orphelines |
| BUG-031 | haute | Sonnet | Fichier vidé : chunks périmés conservés, réindexé à l'infini |
| BUG-032 | haute | Opus | Changement provider/modèle embedding n'invalide pas les vecteurs |
| BUG-033 | haute | Opus | Un fichier poison bloque tous les fichiers suivants d'un job git |
| BUG-034 | moyenne | Sonnet | `list_remote_branches` supprime la clé SSH avant l'exécution git |
| BUG-035 | moyenne | Sonnet | Ref vault explicite `auth_ref` exige à tort un vault par défaut |
| BUG-036 | moyenne | Sonnet | `ssh_username` accepté de bout en bout mais jamais utilisé |
| BUG-037 | moyenne | Opus | Sélecteur de job trie par UUID aléatoire : pas de FIFO, famine |
| BUG-038 | moyenne | Opus | Jobs git contournent le retry/backoff et le circuit-breaker |
| BUG-039 | moyenne | Opus | `strip_separators` détruit les fences `~~~` et frontmatter `---` |
| BUG-040 | moyenne | Sonnet | `strip_html_tags` double-décode et supprime la prose entre `<` et `>` |
| BUG-041 | moyenne | Opus | Estimateur tokens char-ratio : blocs CJK explosent la limite provider |
| BUG-042 | moyenne | Sonnet | Erreurs HTTP 4xx permanentes classées transitoires |
| BUG-043 | basse | Opus | Fonctions/méthodes Python décorées non reconnues par le CodeChunker |
| BUG-044 | basse | Sonnet | `scan_fences` ignore la longueur : fences 4-backticks se ferment tôt |
| BUG-045 | basse | Sonnet | Overlap legacy fait dépasser `max_chars` aux chunks |
| BUG-046 | basse | Opus | Retry rate-limit ignore `Retry-After`, relance des batchs complets |
| BUG-047 | basse | Sonnet | Job avec contexte workspace manquant bloqué en `running` |
| BUG-048 | basse | Sonnet | Récupération au crash orpheline les payloads et perd les documents |
| BUG-049 | **critique** | Opus | Reindex recrée `embeddings` sans migrations → schéma divergent |
| BUG-050 | **critique** | Sonnet | `dict()` sur string jsonb : mapping des résultats de recherche crashe |
| BUG-051 | haute | Opus | `upsert_structured` : CASCADE FK détruit des embeddings gardés |
| BUG-052 | haute | Sonnet | `delete_git_credential` interroge une table `sources` inexistante |
| BUG-053 | haute | Sonnet | `delete_provider_key` référence la colonne supprimée `api_key_ref` |
| BUG-054 | haute | Opus | Secrets de headers webhook `vault` jamais écrits dans Harpocrate |
| BUG-055 | haute | Opus | Contournement SSRF via littéraux IPv6 mappés-IPv4 |
| BUG-056 | haute | Opus | `get_default_vault_name()` renvoie l'api_key_id, utilisé comme nom |
| BUG-057 | moyenne | Sonnet | Vault `create(is_default)` démote le défaut hors transaction |
| BUG-058 | moyenne | Opus | Pool registry : race check-then-create + éviction LRU d'un pool actif |
| BUG-059 | moyenne | Opus | Acquisition de pool imbriquée → deadlock par épuisement |
| BUG-060 | moyenne | Sonnet | I/O synchrone bloquant (méthodes HarpocrateVaults + bcrypt) |
| BUG-061 | moyenne | Sonnet | Cache JWKS OIDC sans TTL ni invalidation sur échec de signature |
| BUG-062 | moyenne | Sonnet | `reindex_workspace` : omettre `api_key_ref` déclenche le drop destructif |
| BUG-063 | moyenne | Sonnet | `JobLogBus` : buffers jamais libérés → croissance mémoire non bornée |
| BUG-064 | basse | Sonnet | `upsert_chunks(append)` : race MAX+1 sur `(path, chunk_index)` |
| BUG-065 | basse | Sonnet | `test_source_connection` : subprocess git en timeout jamais tué |
| BUG-066 | basse | Sonnet | `add/update_source` détecte la branche avec `token=None` (repos privés) |
| BUG-067 | basse | Sonnet | `get_index_status` : `LIMIT 1` sans ORDER BY (source arbitraire) |
| BUG-068 | basse | Sonnet | Dédup d'enrichissement clé sur le hash source (prompt/LLM ignorés) |
| BUG-069 | haute | Opus | Actions webhook passent l'UUID comme `source_name` si `name` null |
| BUG-070 | haute | Opus | AddSourceDialog : défaut `ssh_username` écrase la valeur en édition |
| BUG-071 | moyenne | Sonnet | `credential_ref` non réinitialisé au switch auth → ref envoyée en ssh_key_ref |
| BUG-072 | moyenne | Opus | Détection de branche : races non gardées, pas d'annulation |
| BUG-073 | haute | Sonnet | Détail workspace : pas d'état d'erreur → spinner infini/rendu périmé |
| BUG-074 | moyenne | Sonnet | Playground : `min_score` 0 impossible, saute à 0.7 ; idem top_k |
| BUG-075 | moyenne | Sonnet | WebhookForm : map d'erreurs par index non ré-indexée à la suppression |
| BUG-076 | moyenne | Sonnet | Mutations webhook sans `onError` : création échouée silencieuse |
| BUG-077 | moyenne | Sonnet | CreateWorkspaceDialog : défauts calculés avant chargement des modèles |
| BUG-078 | basse | Sonnet | Toast d'avertissement de branche remplacé (TOAST_LIMIT = 1) |
| BUG-079 | basse | Sonnet | Compteur de headers : clé plurielle `_one` codée en dur |
| BUG-080 | basse | Sonnet | Playground affiche « no LLM » pendant le chargement des configs |
| BUG-081 | basse | Sonnet | TriggerPromptsPanel : `order_index` dupliqué ; erreurs d'ajout avalées |
| BUG-082 | basse | Opus | `CleaningOptionsPanel` jamais monté — feature inaccessible |
| BUG-083 | basse | Sonnet | Page Harpocrate re-sélectionne un vault retiré depuis le cache périmé |
| BUG-084 | **critique** | Sonnet | Caddyfile prod : `handle /mcp` ne matche pas `/mcp/{workspace_id}` |
| BUG-085 | haute | Sonnet | Caddyfile dev : aucune route `/mcp` (absorbée par le catch-all) |
| BUG-086 | moyenne | Sonnet | Caddyfile prod : route `/workspaces/*` morte (timeouts 120s inactifs) |
| BUG-087 | haute | Opus | `smoke-m5e.sh` obsolète : env inexistant + colonnes supprimées |
| BUG-088 | moyenne | Opus | `test-create-lxc.sh` : PAT GitHub dans l'URL de clone (persisté) |
| BUG-089 | moyenne | Sonnet | `dev-deploy.sh` exit 1 après succès si interface ≠ `eth0` |
| BUG-090 | moyenne | Sonnet | `frontend/Dockerfile` : pas de `.dockerignore` (COPY écrase node_modules) |
| BUG-091 | moyenne | Sonnet | Prod : caddy `service_healthy` sans `start_period` → site down au boot lent |
| BUG-092 | basse | Sonnet | `dev-deploy.sh` continue sans `.env` : `--reset` no-op silencieux |
| BUG-093 | basse | Sonnet | `destroy-test.sh` : `sleep 2` fixe → destroy peut échouer sous `set -e` |
| BUG-094 | basse | Sonnet | `fetch-harpocrate-sdk.sh` obsolète : wheel 0.4.0 non consommé |
| BUG-095 | basse | Sonnet | `remote-deploy.ps1` : mot de passe SSH exposé sur la ligne de commande |
| BUG-096 | basse | Sonnet | `docker-compose-dev.yml` : healthcheck postgres sans `start_period` |
| BUG-097 | basse | Sonnet | `dev-deploy.sh` : URLs finales trompeuses (IHM sur `/`, psql sur `postgres`) |

## Notes transversales

- **BUG-022 / BUG-024** : deux faces de la même incohérence de normalisation de `api_key_ref` (4 sites d'appel). Un helper partagé les corrige ensemble.
- **BUG-020 / BUG-052 / BUG-053 / BUG-087** : tous des séquelles de la migration 033 (colonnes `workspaces.api_key_ref` / `api_key_fingerprint` supprimées) que du code référence encore.
- **BUG-023 / BUG-028 / BUG-060** : même famille d'I/O synchrone bloquant sur l'event loop (Harpocrate SDK, bcrypt).
- **BUG-084 / BUG-085** : même fix de routing Caddy (`handle /mcp*`) côté prod et dev.
