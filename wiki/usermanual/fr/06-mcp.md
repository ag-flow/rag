# 06 — Service MCP

Le service RAG expose un serveur **MCP natif** (Model Context Protocol) qui permet à Claude Code de rechercher dans vos corpus documentaires directement depuis le chat, sans aucun outil supplémentaire à installer.

---

## Comprendre le protocole MCP

MCP (Model Context Protocol) est un protocole open source d'Anthropic qui permet aux LLM de se connecter à des sources de données et d'outils externes. Claude Code supporte nativement ce protocole.

ag-flow.rag implémente le transport **Streamable HTTP** (HTTP natif, sans proxy), ce qui signifie :
- Pas de binaire à installer localement
- Un seul fichier de configuration JSON
- Connexion directe au serveur distant

---

## Architecture de la connexion MCP

```
Claude Code (votre machine)
         │
         │  HTTPS POST
         │  Authorization: Bearer <clé-api-workspace>
         ▼
https://rag.votre-domaine.fr/mcp/{workspace_id}
         │
         ├── Valide l'identité (workspace_id dans l'URL)
         ├── Authentifie (clé API dans le header)
         └── Exécute rag_search → retourne chunks
```

Deux informations sont nécessaires :
1. **L'URL du serveur MCP** : contient l'UUID du workspace
2. **Le token d'accès** : une des clés API du workspace

---

## Obtenir les paramètres de connexion

### Via l'interface (recommandé)

1. Ouvrez le workspace dans l'interface
2. Cliquez sur l'onglet **Api**
3. La section **Connexion MCP** en haut de la page affiche :
   - L'**URL du serveur MCP** (prête à copier)
   - La **configuration Claude Code** complète (JSON prêt à coller)

```
┌─ Connexion MCP ─────────────────────────────────────────────────┐
│                                                                   │
│  URL du serveur MCP                                              │
│  ┌───────────────────────────────────────────────────┐ [Copier] │
│  │ https://rag.votre-domaine.fr/mcp/550e8400-e29b... │          │
│  └───────────────────────────────────────────────────┘          │
│                                                                   │
│  Token d'accès → utiliser une clé API ci-dessous                 │
│                                                                   │
│  Config Claude Code (.claude/mcp.json)                           │
│  ┌───────────────────────────────────────────────────┐ [Copier] │
│  │ {                                                 │          │
│  │   "mon-projet": {                                 │          │
│  │     "url": "https://.../mcp/550e8400...",         │          │
│  │     "headers": {                                  │          │
│  │       "Authorization": "Bearer <votre-clé>"       │          │
│  │     }                                             │          │
│  │   }                                               │          │
│  │ }                                                 │          │
│  └───────────────────────────────────────────────────┘          │
└───────────────────────────────────────────────────────────────────┘
```

4. Dans la section **Clés API** ci-dessous, créez ou copiez une clé API
5. Remplacez `<votre-clé>` dans le JSON par la valeur de la clé

### Via l'API

```bash
# Récupérer l'UUID du workspace
WORKSPACE_ID=$(curl -s -H "Authorization: Bearer $RAG_MASTER_KEY" \
  https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet \
  | jq -r '.id')

# Construire l'URL MCP
echo "https://rag.votre-domaine.fr/mcp/$WORKSPACE_ID"

# Obtenir une clé API (liste les clés existantes)
curl -H "Authorization: Bearer $RAG_MASTER_KEY" \
  https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/api-keys
```

---

## Configurer Claude Code

### Méthode 1 : Fichier de projet `.claude/mcp.json`

Créez ou modifiez le fichier `.claude/mcp.json` à la racine de votre projet :

```json
{
  "mcpServers": {
    "mon-projet-rag": {
      "url": "https://rag.votre-domaine.fr/mcp/550e8400-e29b-41d4-a716-446655440000",
      "headers": {
        "Authorization": "Bearer ws_votre_cle_api_workspace"
      }
    }
  }
}
```

> Ce fichier configure le MCP uniquement pour ce projet. Chaque projet peut avoir sa propre configuration.

### Méthode 2 : Configuration globale `~/.claude/mcp.json`

Pour accéder au RAG depuis n'importe quel projet :

```json
{
  "mcpServers": {
    "harpocrate-docs": {
      "url": "https://rag.votre-domaine.fr/mcp/uuid-workspace-harpocrate",
      "headers": {
        "Authorization": "Bearer ws_cle_harpocrate"
      }
    },
    "agflow-code": {
      "url": "https://rag.votre-domaine.fr/mcp/uuid-workspace-agflow",
      "headers": {
        "Authorization": "Bearer ws_cle_agflow"
      }
    }
  }
}
```

### Méthode 3 : Plusieurs workspaces dans un projet

Vous pouvez connecter plusieurs workspaces RAG dans le même fichier de configuration :

```json
{
  "mcpServers": {
    "docs-fr": {
      "url": "https://rag.votre-domaine.fr/mcp/uuid-workspace-docs-fr",
      "headers": {
        "Authorization": "Bearer ws_cle_docs_fr"
      }
    },
    "code-source": {
      "url": "https://rag.votre-domaine.fr/mcp/uuid-workspace-code",
      "headers": {
        "Authorization": "Bearer ws_cle_code"
      }
    }
  }
}
```

Claude Code verra alors deux outils distincts : `docs-fr__rag_search` et `code-source__rag_search`.

---

## Utiliser le RAG dans Claude Code

Une fois configuré, Claude Code peut appeler l'outil `rag_search` automatiquement ou sur demande.

### Appel automatique

Claude Code détecte quand une question peut bénéficier d'une recherche RAG et appelle l'outil de façon autonome.

### Appel explicite

Vous pouvez demander explicitement à Claude Code de chercher dans le corpus :

```
"Cherche dans le corpus comment fonctionne la gestion des sessions"
"Trouve les informations sur la configuration OIDC dans la documentation"
"D'après le code indexé, comment est implémenté le chunking ?"
```

### Paramètres de l'outil `rag_search`

| Paramètre | Type | Défaut | Description |
|---|---|---|---|
| `query` | string | *requis* | La question ou la requête de recherche |
| `top_k` | integer | 5 | Nombre de chunks à retourner (max 50) |
| `min_score` | number | 0.3 | Score de similarité minimum (0 à 1) |

### Exemples d'utilisation dans Claude Code

```
# Dans Claude Code
> Cherche dans la documentation comment configurer les webhooks sortants

[rag_search appelé automatiquement]
[5 chunks retournés avec scores 0.82, 0.79, 0.71, 0.68, 0.64]

Claude répond en s'appuyant sur les chunks trouvés...
```

---

## Instance auto-hébergée

ag-flow.rag est open source. Si vous hébergez votre propre instance, adaptez l'URL en conséquence :

```json
{
  "mcpServers": {
    "mon-rag-local": {
      "url": "http://192.168.1.100:8000/mcp/550e8400-e29b-41d4-a716-446655440000",
      "headers": {
        "Authorization": "Bearer ws_votre_cle_api"
      }
    }
  }
}
```

> **HTTP vs HTTPS :** En développement local, HTTP est acceptable. En production, utilisez toujours HTTPS pour protéger votre clé API en transit.

---

## Résolution des problèmes

### Claude Code ne voit pas l'outil MCP

1. Vérifiez que le fichier `.claude/mcp.json` est bien au bon emplacement
2. Rechargez Claude Code (fermer/rouvrir)
3. Vérifiez que l'URL est accessible : `curl -v https://rag.votre-domaine.fr/mcp/{workspace_id}`

### Erreur d'authentification (401)

- Vérifiez que la clé API n'a pas été révoquée (onglet **Api** du workspace)
- Assurez-vous que le header contient bien `Bearer ` (avec l'espace) avant la clé
- Si la clé est en grace period (rotation en cours), elle fonctionne encore — vérifiez l'orthographe

### Erreur workspace introuvable (404)

- Vérifiez l'UUID du workspace (onglet **Api** > URL du serveur MCP)
- Assurez-vous que le workspace existe et n'a pas été supprimé

### Résultats vides ou peu pertinents

- Vérifiez que des sources git sont configurées et que des jobs d'indexation ont réussi
- Réduisez `min_score` (essayez 0.2 ou 0.1) — certains modèles d'embedding donnent des scores plus bas
- Augmentez `top_k` pour récupérer plus de candidats
- Vérifiez la langue de votre query par rapport au corpus indexé

### Le service MCP est lent

- Les premiers appels résolvent les secrets depuis Harpocrate — normal (cache ensuite)
- Vérifiez la latence réseau vers votre serveur RAG
- Vérifiez les logs du service : `docker compose logs rag-service --tail=50`

---

## Paramètre min_score — guide de réglage

Le score de similarité (cosinus) varie selon le modèle d'embedding :

| Modèle | Plage typique | min_score recommandé |
|---|---|---|
| `openai/text-embedding-3-small` | 0.2 — 0.6 | 0.3 |
| `openai/text-embedding-3-large` | 0.2 — 0.6 | 0.3 |
| `voyage/voyage-3` | 0.4 — 0.8 | 0.5 |
| `voyage/voyage-code-3` | 0.3 — 0.7 | 0.4 |
| `ollama/nomic-embed-text` | 0.1 — 0.5 | 0.2 |

**Règle générale :**
- Score trop élevé → aucun résultat (le plus fréquent)
- Score trop bas → résultats non pertinents
- Commencez à 0.3, ajustez selon les retours

---

## Référence rapide

```
URL du serveur MCP :
  https://{rag_public_url}/mcp/{workspace_uuid}

Header d'authentification :
  Authorization: Bearer {api_key_workspace}

Outil disponible :
  rag_search(query, top_k=5, min_score=0.3)

Format de réponse :
  [path/fichier.md — chunk 2 — score 0.87]
  Contenu du chunk ici...

  ---

  [autre/fichier.md — chunk 0 — score 0.81]
  ...
```

---

## Prochaine étape

→ [07 — Playground](07-playground.md)
