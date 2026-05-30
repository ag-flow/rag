# RAG Service — RAG Playground

## Principe

Interface de chat intégrée à l'IHM permettant d'avoir une conversation avec un LLM ancré sur le RAG d'un workspace. Chaque message de l'utilisateur déclenche une recherche sémantique — les chunks pertinents sont injectés dans le contexte avant d'appeler le LLM.

La session est **volatile** — l'historique disparaît à la fermeture. Aucune persistance en base.

Accessible aux rôles OIDC `rag-admin` et `rag-viewer`.

### Usages

- Poser des questions ad hoc sur le corpus
- Vérifier qu'un document est correctement indexé et retrouvable
- Tester la qualité des chunks et des scores de similarité

---

## Providers LLM supportés

| Provider | Modèles proposés |
|---|---|
| **Claude** | claude-sonnet-4-5, claude-opus-4-5 |
| **OpenAI (Codex)** | gpt-4o, gpt-4o-mini, o1 |
| **Azure OpenAI** | gpt-4o, gpt-4o-mini (déployés sur l'instance Azure) |
| **Ollama** | Modèles disponibles sur l'instance configurée |

La config des LLM autorisés par workspace se fait exclusivement via l'IHM (rôle `rag-admin`).

---

## Modèle de données — table `workspace_llm_configs`

```sql
CREATE TABLE workspace_llm_configs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  provider      TEXT NOT NULL,       -- "claude" | "openai" | "azure-openai" | "ollama"
  model         TEXT NOT NULL,       -- ex: "claude-sonnet-4-5"
  base_url      TEXT,                -- null sauf ollama
  api_key_ref   TEXT,                -- clé logique Harpocrate (null pour ollama local)
  enabled       BOOLEAN DEFAULT true,
  created_at    TIMESTAMPTZ DEFAULT now(),
  UNIQUE(workspace_id, provider, model)
);
```

Le path vault des api_keys LLM est structuré ainsi :

```
${vault://harpocrate-1:/workspaces/{workspace}/llm/{provider}/apikey}
```

---

## API Playground

### Envoyer un message

```
POST /workspaces/{name}/playground/chat
Authorization: OIDC (rag-admin ou rag-viewer)
```

### Requête

```json
{
  "message": "comment fonctionne le gap handling ?",
  "history": [
    {
      "role": "user",
      "content": "explique moi la réplication dans Harpocrate"
    },
    {
      "role": "assistant",
      "content": "La réplication dans Harpocrate repose sur MQTT avec QoS 1..."
    }
  ],
  "llm": {
    "provider": "claude",
    "model": "claude-sonnet-4-5"
  },
  "top_k": 5,
  "min_score": 0.7
}
```

L'historique est géré côté client — le frontend accumule les échanges et les renvoie à chaque appel. Le service est stateless.

### Réponse

```json
{
  "message": "comment fonctionne le gap handling ?",
  "answer": "Le gap handling repose sur le sync_shelf qui maintient...",
  "chunks": [
    {
      "path": "architecture/replication.md",
      "chunk_index": 2,
      "content": "Le sync_shelf maintient les messages reçus hors séquence...",
      "score": 0.94
    },
    {
      "path": "concepts/emitter-id.md",
      "chunk_index": 0,
      "content": "Chaque nœud Harpocrate émet avec un (emitter_id, seq) unique...",
      "score": 0.87
    }
  ],
  "usage": {
    "prompt_tokens": 1580,
    "completion_tokens": 284
  }
}
```

---

## Construction du prompt LLM

À chaque message, le service :

1. Interroge le RAG avec le message courant (`top_k` chunks)
2. Construit le prompt avec contexte + historique + question
3. Appelle le LLM

```
[System]
Tu es un assistant expert. Réponds en te basant uniquement 
sur le contexte fourni. Si la réponse n'est pas dans le contexte, 
dis-le explicitement.

[Contexte RAG — extrait à chaque message]
---
[chunk 1 — path: architecture/replication.md]
Le sync_shelf maintient les messages reçus hors séquence...

[chunk 2 — path: concepts/emitter-id.md]
Chaque nœud Harpocrate émet avec un (emitter_id, seq) unique...
---

[Historique de conversation]
User: explique moi la réplication dans Harpocrate
Assistant: La réplication dans Harpocrate repose sur MQTT avec QoS 1...

[Message courant]
User: comment fonctionne le gap handling ?
```

---

## IHM — Interface Chat

### Disposition

```
┌─────────────────────────────────────────────────────┐
│  Workspace: [harpocrate ▾]   LLM: [Claude Sonnet ▾] │
│  top_k: [5]   min_score: [0.7]          [Réinitialiser]│
├─────────────────────────────────────────────────────┤
│                                                     │
│  Assistant: Bonjour, posez vos questions sur le     │
│  corpus harpocrate.                                 │
│                                                     │
│  Vous: explique moi la réplication                  │
│                                                     │
│  Assistant: La réplication repose sur MQTT...       │
│  [▸ Chunks utilisés (2)]                            │
│                                                     │
│  Vous: et le gap handling ?                         │
│                                                     │
│  Assistant: Le gap handling repose sur sync_shelf...│
│  [▸ Chunks utilisés (2)]                            │
│                                                     │
├─────────────────────────────────────────────────────┤
│  [Votre message...                          Envoyer]│
└─────────────────────────────────────────────────────┘
```

### Comportement

- Chunks repliés sous chaque réponse — un clic déplie avec path + score + contenu
- Bouton **Réinitialiser** — vide l'historique côté client, repart d'une session propre
- Indicateur de chargement pendant l'appel LLM
- Si aucun chunk pertinent trouvé (`score < min_score`) → le LLM est informé dans le prompt, sa réponse le signale
- Tokens consommés affichés en pied de chaque réponse
- Seuls les LLM **utilisables** apparaissent dans le sélecteur — `enabled: true` ET api_key renseignée (sauf Ollama local) ET base_url renseignée pour Ollama. Un LLM configuré à moitié est affiché en grisé dans l'écran de config avec un indicateur "incomplet"

---

## Sécurité

- Endpoint accessible aux rôles OIDC `rag-admin` et `rag-viewer`
- Les api_keys LLM sont résolues depuis Harpocrate au moment de l'appel — jamais exposées côté client
- Aucune donnée de conversation n'est persistée en base