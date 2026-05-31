# 07 — Playground

Le Playground est une interface de chat intégrée qui vous permet d'interroger vos corpus RAG en langage naturel, avec le contexte injecté automatiquement dans la conversation.

---

## Accéder au Playground

1. Ouvrez un workspace dans l'interface
2. Cliquez sur l'onglet **Playground**
3. Sous-onglet **Chat**

> **Prérequis :** Au moins un LLM doit être configuré dans le sous-onglet **LLM Config** du Playground.

---

## Interface du Chat

```
┌─────────────────────────────────────────────────────────────────┐
│ LLM: [openai / gpt-4o ▾]  top_k: [5]  min_score: [0,3]  Reset │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│                          Vous : test                             │
│                                                                   │
│  Je suis désolé, mais aucun contexte pertinent n'a              │
│  été trouvé dans le corpus pour votre demande.                   │
│  › Used chunks (0)                                               │
│  Tokens: prompt=37 / completion=27                               │
│                                                                   │
│                    Vous : de quoi parle le corpus ?              │
│                                                                   │
│  [Réponse basée sur les chunks trouvés...]                       │
│  › Used chunks (3)                                               │
│  Tokens: prompt=892 / completion=156                             │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│ [Votre message...                                       Envoyer] │
└─────────────────────────────────────────────────────────────────┘
```

### Paramètres de la barre de contrôle

| Paramètre | Description | Valeur par défaut |
|---|---|---|
| **LLM** | Sélectionne le modèle de langage pour la réponse | Premier LLM activé |
| **top_k** | Nombre de chunks RAG à injecter dans le contexte | 5 |
| **min_score** | Score de similarité minimum pour inclure un chunk | 0.3 |
| **Reset** | Efface l'historique de la conversation | — |

### Interpréter les chunks utilisés

Cliquez sur **Used chunks (N)** pour voir les extraits de corpus qui ont alimenté la réponse :

```
› Used chunks (3)
  ┌──────────────────────────────────────────────────────────┐
  │ docs/architecture/replication.md               score 0.87 │
  │ Le sync_shelf maintient les messages reçus hors          │
  │ séquence. Quand un message (seq=42) arrive alors que     │
  │ le dernier confirmé est seq=38...                        │
  ├──────────────────────────────────────────────────────────┤
  │ docs/concepts/emitter-id.md                    score 0.79 │
  │ Chaque nœud Harpocrate émet avec un (emitter_id, seq)    │
  │ unique. La combinaison garantit l'unicité globale...     │
  └──────────────────────────────────────────────────────────┘
```

---

## Configurer les LLM disponibles

### Via l'interface

1. Onglet **Playground** > sous-onglet **LLM Config**
2. Cliquez **+ Ajouter une configuration LLM**
3. Remplissez les champs :

| Champ | Description |
|---|---|
| **Provider** | `openai` / `claude` / `azure-openai` / `ollama` |
| **Modèle** | Identifiant du modèle selon le provider |
| **URL de base** | Uniquement pour Ollama ou Azure OpenAI |
| **Clé API** | Sélectionner dans les clés API du coffre Harpocrate |
| **Activé** | Active/désactive ce LLM dans le sélecteur |

### LLM supportés

**OpenAI :**

| Modèle | Description |
|---|---|
| `gpt-4o` | GPT-4o — excellent rapport qualité/coût |
| `gpt-4o-mini` | GPT-4o Mini — plus rapide, moins cher |
| `o1` | o1 — raisonnement avancé |

**Claude (Anthropic) :**

| Modèle | Description |
|---|---|
| `claude-sonnet-4-6` | Claude Sonnet 4.6 — excellent pour le RAG |
| `claude-opus-4-8` | Claude Opus 4.8 — maximum de qualité |
| `claude-haiku-4-5` | Claude Haiku 4.5 — rapide et économique |

**Ollama (local) :**

Utilisez Ollama pour des données sensibles ou pour zéro coût :

| Modèle | Description |
|---|---|
| `llama3.2` | Llama 3.2 — polyvalent |
| `qwen2.5-coder` | Qwen 2.5 Coder — optimisé pour le code |
| `mistral` | Mistral — bon pour le français |

### Via l'API

```bash
# Ajouter GPT-4o
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/llm-configs \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "openai",
    "model": "gpt-4o",
    "api_key_ref": "openai_api_key",
    "enabled": true
  }'

# Ajouter Claude Sonnet
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/llm-configs \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "claude",
    "model": "claude-sonnet-4-6",
    "api_key_ref": "anthropic_api_key",
    "enabled": true
  }'

# Ajouter Ollama local
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/llm-configs \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "ollama",
    "model": "llama3.2",
    "base_url": "http://192.168.1.100:11434",
    "enabled": true
  }'
```

---

## Utiliser le Playground efficacement

### Bonnes requêtes

Le Playground excelle pour des questions :
- **Factuelles** sur le contenu du corpus : *"Comment est configuré le clustering Redis ?"*
- **Conceptuelles** : *"Quelle est la différence entre les modes de réplication ?"*
- **De code** : *"Montre-moi un exemple d'utilisation de l'API d'indexation"*
- **De recherche** : *"Quels fichiers concernent la gestion des erreurs ?"*

### Conversation multi-tours

L'historique est accumulé côté client pendant la session. Vous pouvez poser des questions de suivi :

```
Vous : Comment fonctionne l'authentification ?
Assistant : [explique avec chunks RAG]

Vous : Et pour le cas des tokens expirés ?
Assistant : [répond en contexte, avec nouveaux chunks]

Vous : Donne-moi un exemple de code
Assistant : [basé sur les chunks de code trouvés]
```

### Réinitialiser la conversation

Le bouton **Reset** efface l'historique mais ne vide pas le corpus. Utile pour démarrer un nouveau sujet sans biais de l'historique.

---

## Accès via l'API (usage programmatique)

Le Playground chat est aussi accessible via API pour les intégrations :

```bash
curl -X POST https://rag.votre-domaine.fr/api/workspaces/mon-projet/playground/chat \
  -H "Authorization: Bearer $SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Comment fonctionne la réplication ?",
    "history": [],
    "llm": {
      "provider": "openai",
      "model": "gpt-4o"
    },
    "top_k": 5,
    "min_score": 0.3
  }'
```

Réponse :
```json
{
  "message": "Comment fonctionne la réplication ?",
  "answer": "La réplication repose sur le sync_shelf qui maintient...",
  "chunks": [
    {
      "path": "docs/architecture/replication.md",
      "chunk_index": 2,
      "content": "Le sync_shelf maintient les messages...",
      "score": 0.87
    }
  ],
  "usage": {
    "prompt_tokens": 892,
    "completion_tokens": 156
  }
}
```

> **Note :** L'authentification pour cette API est la session OIDC (rôle `rag-viewer` ou `rag-admin`), pas la master key.

---

## Limitations

- **Historique volatil :** la conversation est perdue à la fermeture de l'onglet ou rechargement de la page
- **Pas de persistance :** aucun historique n'est sauvegardé côté serveur
- **Contexte limité :** le nombre de chunks injectés est limité par `top_k`

Pour un usage production avec historique persistant, utilisez directement l'API `/mcp` ou le SDK MCP depuis votre application.

---

## Prochaine étape

→ [08 — Webhooks sortants](08-webhooks.md)
