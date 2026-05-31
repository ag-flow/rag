# 13 — Déduplication par hash

La déduplication est un mécanisme central du service RAG qui évite de gaspiller des crédits d'embedding sur des documents dont le contenu n'a pas changé.

---

## Principe

Chaque document indexé est associé à un **hash SHA-256 de son contenu**. Avant d'appeler l'API d'embedding (OpenAI, Voyage, etc.), le service compare le hash du document entrant avec celui stocké en base. Si les hashes sont identiques, l'embedding est sauté.

```
Document reçu (path + content)
        │
        ▼
hash = SHA-256(content)
        │
        ├── hash == hash stocké pour ce path ?
        │         ↓ OUI
        │   status: "skipped" → zéro appel embedding
        │
        └── hash différent ou path inconnu ?
                  ↓ NON
            Chunking → Embedding → Upsert pgvector
            → Mise à jour du hash stocké
```

Sur un workspace de 61 fichiers avec 3 modifications :
- 3 fichiers → embedding (changed)
- 58 fichiers → skip (contenu identique)
- **95% d'appels embedding économisés**

---

## Ce qui déclenche la déduplication

### Lors d'une sync git

Le service récupère le diff git entre le dernier commit connu et le commit courant. Seuls les fichiers du diff sont soumis au test de hash :

| Action git | Comportement |
|---|---|
| Fichier ajouté | Hash absent → indexation complète |
| Fichier modifié | Hash différent → réindexation complète du fichier |
| Fichier renommé | Ancien path supprimé, nouveau path indexé |
| Fichier supprimé | Chunks supprimés de pgvector, hash supprimé |
| Fichier inchangé dans le diff | Non traité (jamais vu par le moteur) |

### Lors d'un push manuel (`/workspaces/{name}/index`)

Même logique : le hash du `content` fourni est comparé au hash stocké.

```json
// Réponse si contenu inchangé
{"path": "docs/guide.md", "status": "skipped", "reason": "content_unchanged"}

// Réponse si contenu nouveau/modifié
{"path": "docs/guide.md", "status": "indexed", "chunks": 4, "hash": "sha256:abc..."}
```

---

## Lire les statistiques dans les jobs

L'onglet **Jobs** du workspace affiche les compteurs de déduplication pour chaque job :

| Colonne | Description |
|---|---|
| **Fichiers changés** | Documents effectivement re-indexés (embedding appelé) |
| **Fichiers skippés** | Documents ignorés car contenu identique (zéro embedding) |

Exemple :
```
Job 2026-05-31 09:00 (done, 1.2s)
├── Déclenché par : git
├── Fichiers changés  : 3
└── Fichiers skippés  : 58
```

---

## Stockage du hash

La table `indexed_documents` dans la base de configuration (`rag_config`) stocke le hash de chaque document :

```sql
indexed_documents
├── workspace_id   UUID
├── path           TEXT          ← clé de déduplication (path relatif dans le repo)
├── content_hash   TEXT          ← SHA-256 hexadécimal
├── indexer_used   TEXT          ← "openai/text-embedding-3-small" (snapshot)
├── indexed_at     TIMESTAMPTZ   ← dernière date d'indexation effective
└── UNIQUE(workspace_id, path)
```

### Rôle du champ `indexer_used`

Ce champ enregistre le provider+modèle utilisé lors de la dernière indexation. Si le provider ou le modèle change, les hashes deviennent invalides (les vecteurs existants sont incompatibles avec les nouveaux embeddings) → réindexation forcée.

---

## Quand les hashes sont invalidés

### 1. Changement de modèle d'embedding

Si vous changez le provider ou modèle d'indexation d'un workspace (ce qui nécessite `?confirm=true`), **tous les hashes sont réinitialisés** et tout le corpus est réindexé.

```
409 Conflict
{
  "error": "indexer_change_requires_reindex",
  "current": "openai/text-embedding-3-small (dim=1536)",
  "requested": "voyage/voyage-3 (dim=1024)",
  "documents_count": 61,
  "action": "POST /workspaces/mon-projet/reindex?confirm=true"
}
```

### 2. Changement de configuration chunking

Modifier la stratégie ou les paramètres de chunking invalide aussi les hashes (voir [04 — Workspaces > Chunking](04-workspaces.md)).

### 3. Réindexation manuelle

```bash
# Force la réindexation de tout le corpus (ignore les hashes)
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/reindex \
  -H "Authorization: Bearer $RAG_MASTER_KEY"
```

---

## Forcer la réindexation d'un document spécifique

Si un document doit être réindexé sans que son contenu ait changé (ex : après une correction de configuration), utilisez l'API de push avec un contenu légèrement modifié, ou passez par la réindexation complète du workspace.

Il n'existe pas d'endpoint pour invalider le hash d'un seul document. La réindexation complète est le mécanisme prévu.

---

## Déduplication des enrichissements LLM

Le même principe s'applique aux **enrichissements LLM** (voir [09 — Enrichissement LLM](09-enrichissement.md)) :

- Si le contenu brut d'un fichier n'a pas changé → les prompts d'enrichissement ne sont **pas réexécutés**
- Enrichissements existants conservés

```
Job avec triggers .cs
├── src/UserService.cs              → hash identique → skip
│   ├── ::documentation             → conservé (pas réexécuté)
│   └── ::public_methods            → conservé
├── src/OrderService.cs             → hash différent → réindexé
│   ├── ::documentation             → prompt réexécuté (Claude Opus)
│   └── ::public_methods            → prompt réexécuté (GPT-4o)
└── src/Config.cs (supprimé)       → chunks + enrichissements supprimés
```

Si un prompt retourne un résultat **vide** (après le changement) :
- L'enrichissement précédent est **supprimé** (pas de données obsolètes)
- Le job signale ce prompt comme `empty`

---

## Impact sur les coûts

La déduplication est l'un des principaux leviers de réduction de coût du service RAG :

| Scénario | Sans déduplication | Avec déduplication |
|---|---|---|
| Sync quotidienne, 100 fichiers, 2 modifiés | 100 appels embedding | 2 appels embedding |
| Push manuel, fichier inchangé | 1 appel embedding | 0 appel |
| Réindexation complète (forcer) | 100 appels | 100 appels (inévitable) |

Pour un corpus de **1000 documents** avec **10 modifications par jour** :
- Sans déduplication : ~30 000 appels embedding/mois
- Avec déduplication : ~300 appels embedding/mois (**100× moins**)

---

## Prochaine étape

→ [14 — Observabilité](14-observabilite.md)
