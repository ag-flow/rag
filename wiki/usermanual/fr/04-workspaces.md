# 04 — Workspaces

Un **workspace** est l'unité de base du service RAG. Chaque workspace correspond à un corpus documentaire isolé avec son propre modèle d'embedding, ses sources git, ses clés API et ses paramètres.

---

## Comprendre les workspaces

### Isolation totale

Chaque workspace dispose de :
- Sa propre **base de données pgvector** (ex : `rag_mon-projet`)
- Son propre **modèle d'embedding** (défini à la création, immutable)
- Ses propres **sources git** surveillées
- Ses propres **clés API** multi-rotation
- Ses propres **webhooks**, **triggers** et **LLM configs**

### Cas d'usage typiques

| Workspace | Corpus | Provider recommandé |
|---|---|---|
| `harpocrate-docs` | Documentation Harpocrate (Markdown) | `voyage/voyage-3` |
| `agflow-code` | Code source ag.flow.docker | `voyage/voyage-code-3` |
| `internal-docs` | Docs internes sensibles | `ollama/qwen2.5-coder` |
| `public-kb` | Base de connaissances publique | `openai/text-embedding-3-small` |

---

## Créer un workspace

### Via l'interface

1. Cliquez sur **+ New** dans la sidebar
2. Remplissez le formulaire :

**Nom du workspace**
- Minuscules, chiffres et tirets autorisés
- Exemples : `mon-projet`, `harpocrate-docs`, `agflow-v2`
- Ce nom est utilisé dans les URLs et ne peut pas être changé

**Provider et modèle d'indexation** (choix définitif)

Voir le tableau complet des providers dans [02 — Première configuration](02-premiere-configuration.md#étape-5--créer-le-premier-workspace).

**Clé API du provider**
- Sélectionnez parmi les clés API configurées dans votre coffre Harpocrate
- Si vide, configurez d'abord une clé via **Paramètres > Clés API providers**

**Configuration Reranking** (optionnel)
- Améliore la précision des résultats en appliquant un modèle de re-classement après la recherche vectorielle
- Providers disponibles : Cohere, Voyage, Ollama
- `top_k pre-rerank` : nombre de candidats récupérés avant reranking (recommandé : 20-50)

3. Cliquez **Créer le workspace**

Le service crée automatiquement la base de données pgvector dédiée.

### Via l'API

```bash
# Workspace minimal (OpenAI)
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "mon-projet",
    "indexer": {
      "provider": "openai",
      "model": "text-embedding-3-small",
      "api_key_ref": "openai_embedding_key"
    }
  }'
```

```bash
# Workspace avec Voyage + reranking Cohere
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "code-search",
    "indexer": {
      "provider": "voyage",
      "model": "voyage-code-3",
      "api_key_ref": "voyage_api_key"
    },
    "rerank": {
      "provider": "cohere",
      "model": "rerank-english-v3.0",
      "api_key_ref": "cohere_rerank_key",
      "top_k_pre_rerank": 25
    }
  }'
```

```bash
# Workspace avec Ollama local (données sensibles, zéro coût)
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "docs-internes",
    "indexer": {
      "provider": "ollama",
      "model": "nomic-embed-text",
      "base_url": "http://192.168.1.100:11434"
    }
  }'
```

---

## Onglets du panneau workspace

En cliquant sur un workspace dans la sidebar, vous accédez au panneau de détail avec les onglets suivants :

### Onglet Détail

Affiche les informations générales du workspace :

- **Statistiques** : nombre de sources, nombre de documents indexés, date de dernière indexation
- **Identifiants** : nom et UUID du workspace
- **Modèle d'indexation** : provider, modèle, URL de base, référence clé API (en lecture seule — immutable)
- **Configuration Reranking** : provider, modèle, top_k pre-rerank (en lecture seule — immutable)

### Onglet Git sources

Gestion des dépôts git surveillés. Voir [05 — Sources git](05-sources-git.md).

### Onglet Jobs

Historique des indexations :

| Colonne | Description |
|---|---|
| Statut | `pending` / `running` / `done` / `error` |
| Déclenché par | `schedule` / `webhook` / `manual` / `push` / `reindex` |
| Fichiers changés | Nombre de fichiers nouvellement indexés |
| Fichiers skippés | Fichiers identiques (déduplication par hash) |
| Durée | Temps de traitement |

Cliquez sur un job pour voir les détails : liste des fichiers traités, erreurs éventuelles.

### Onglet Chunking

La configuration de chunking détermine comment les documents sont découpés avant l'embedding. Ce paramétrage est **important** : il affecte la qualité des résultats de recherche et ne peut être modifié sans réindexation complète du corpus.

#### Stratégies de chunking

| Stratégie | Description | Usage recommandé |
|---|---|---|
| `paragraph` | Découpe par paragraphes, respecte les sauts de ligne doubles | Texte général, code source, logs |
| `markdown` | Découpe en respectant la structure des titres Markdown | Documentation `.md`, wikis, READMEs |

#### Paramètres

| Paramètre | Défaut | Contrainte | Description |
|---|---|---|---|
| **Taille maximale** (`max_chars`) | 2000 caractères | > 0 | Longueur maximale d'un chunk en caractères |
| **Taille minimale** (`min_chars`) | 200 caractères | ≥ 0, < max | Chunks plus courts que cette valeur sont fusionnés avec le suivant |
| **Chevauchement** (`overlap_chars`) | 200 caractères | ≥ 0, < max | Nombre de caractères répétés entre deux chunks consécutifs |

> **Stratégie markdown uniquement :** champ `heading_levels` (dans extras) : liste des niveaux de titres qui déclenchent une coupe (ex : `[1, 2]` = couper sur H1 et H2).

#### Conseils de configuration

| Type de corpus | Stratégie | max_chars | overlap_chars |
|---|---|---|---|
| Documentation Markdown | `markdown` | 2000 | 200 |
| Code source | `paragraph` | 1500 | 150 |
| Articles / Texte long | `paragraph` | 2500 | 300 |
| Q&A / FAQ courtes | `paragraph` | 800 | 100 |

**Règles générales :**
- Plus `max_chars` est grand → chunks plus contextuels, mais recherche moins précise
- Plus `overlap_chars` est grand → meilleure continuité entre chunks, mais plus de tokens utilisés
- `min_chars` évite les chunks trop courts qui pollueraient les résultats

#### Modifier la configuration

**Via l'interface :** Onglet Chunking → modifier les valeurs → **Enregistrer**

Si le workspace a déjà des documents indexés, une confirmation est requise (réindexation complète déclenchée automatiquement).

**Via l'API :**
```bash
curl -X PUT "https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/chunking-config" \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": "markdown",
    "max_chars": 2000,
    "min_chars": 200,
    "overlap_chars": 200
  }'
```

Si des documents existent et que le changement nécessite une réindexation :
```bash
# 409 Conflict → forcer avec confirm=true
curl -X PUT ".../chunking-config?confirm=true" \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -d '{"strategy": "markdown", "max_chars": 2000, "min_chars": 200, "overlap_chars": 200}'
```

### Onglet Webhooks

Configuration des notifications post-indexation. Voir [08 — Webhooks sortants](08-webhooks.md).

### Onglet Playground

Interface de chat RAG ancré sur le corpus. Voir [07 — Playground](07-playground.md).

### Onglet Triggers

Configuration des enrichissements LLM par extension de fichier. Voir [09 — Enrichissement LLM](09-enrichissement.md).

### Onglet Api

Gestion des clés API du workspace et configuration MCP. Voir [06 — Service MCP](06-mcp.md).

---

## Gestion des clés API workspace

### Principe multi-clés

Chaque workspace peut avoir plusieurs clés API nommées. Cela permet de :
- Donner des clés distinctes à différents agents/services
- Révoquer une clé compromise sans perturber les autres
- Faire une rotation planifiée sans interruption

### Créer une clé API

1. Onglet **Api** du workspace
2. Cliquez **Ajouter une clé**
3. Donnez un nom descriptif (ex : `agent-agflow`, `ci-cd`, `claude-code`)
4. La clé est affichée **une seule fois** — copiez-la immédiatement

### Statuts des clés

| Statut | Description |
|---|---|
| 🟢 **Active** | Clé valide, utilisable |
| 🟡 **Grace period** | Clé en cours de rotation (72h de grâce, puis expirée) |
| 🔴 **Révoquée** | Clé révoquée immédiatement |
| ⚪ **Expirée** | Clé expirée (rotation ancienne) |

### Rotation d'une clé

La rotation crée une nouvelle clé et place l'ancienne en **grace period de 72 heures**. Pendant ce délai, les deux clés fonctionnent, vous laissant le temps de mettre à jour vos clients.

1. Cliquez l'icône de rotation (🔄) sur la clé
2. Confirmez la rotation
3. **Copiez la nouvelle clé** — elle n'est affichée qu'une fois
4. Mettez à jour vos configurations Claude Code / agents dans les 72h

### Révoquer une clé

La révocation est immédiate et irréversible. Utilisez-la en cas de compromission.

1. Cliquez l'icône de révocation (✕) sur la clé
2. Confirmez la révocation dans la boîte de dialogue

---

## Réindexation complète

Si vous changez le modèle d'embedding (après confirmation de vos clés Harpocrate), ou si vous souhaitez réindexer tout le corpus :

```bash
# Forcer une réindexation complète
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/reindex \
  -H "Authorization: Bearer $RAG_MASTER_KEY"
```

> **Note :** Cela efface tous les vecteurs existants et réindexe depuis zéro. L'opération peut prendre du temps selon la taille du corpus.

---

## Supprimer un workspace

> **Attention :** La suppression est irréversible. Elle supprime la base pgvector, tous les vecteurs, toutes les clés API et toutes les configurations associées.

**Via l'interface :**
1. Menu `⋮` dans le header du workspace
2. **Supprimer le workspace**
3. Confirmer en tapant le nom du workspace

**Via l'API :**
```bash
curl -X DELETE https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet \
  -H "Authorization: Bearer $RAG_MASTER_KEY"
```

---

## Changer le modèle d'indexation

Le modèle d'embedding est normalement immutable (dimension incompatible entre providers). Si vous devez absolument en changer :

```bash
# Tenter le changement (retourne une erreur explicative si des vecteurs existent)
curl -X PATCH https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"indexer": {"provider": "voyage", "model": "voyage-3", "api_key_ref": "voyage_key"}}'

# Si 409 Conflict → forcer avec reindexation complète
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/reindex?confirm=true \
  -H "Authorization: Bearer $RAG_MASTER_KEY"
```

---

## Prochaine étape

→ [05 — Sources git](05-sources-git.md)
