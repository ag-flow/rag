# RAG Service — API MCP

## Rôle

L'endpoint MCP est l'interface de **recherche sémantique** consommée par les agents ag.flow et Claude Code. Il permet d'interroger un ou plusieurs workspaces en une seule requête.

---

## Endpoint

```
POST /mcp
```

---

## Requête — workspace unique

```json
{
  "workspace": "harpocrate",
  "api_key": "ws_xxx...",
  "query": "comment fonctionne le gap handling dans la réplication ?",
  "top_k": 5
}
```

## Requête — multi-workspaces

L'agent n'est pas limité à un seul workspace. Il peut interroger plusieurs workspaces en parallèle :

```json
{
  "workspaces": [
    { "name": "harpocrate",     "api_key": "ws_aaa..." },
    { "name": "ag-flow-docker", "api_key": "ws_bbb..." }
  ],
  "query": "comment les agents accèdent aux secrets ?",
  "top_k": 5
}
```

Les résultats sont fusionnés et re-rankés par score de similarité cosinus.

---

## Réponse

```json
{
  "query": "comment fonctionne le gap handling dans la réplication ?",
  "results": [
    {
      "workspace": "harpocrate",
      "path": "architecture/replication.md",
      "chunk_index": 2,
      "content": "Le sync_shelf maintient les messages reçus hors séquence...",
      "score": 0.94
    },
    {
      "workspace": "harpocrate",
      "path": "concepts/emitter-id.md",
      "chunk_index": 0,
      "content": "Chaque nœud Harpocrate émet avec un (emitter_id, seq) unique...",
      "score": 0.87
    }
  ]
}
```

---

## Paramètres

| Paramètre | Type | Défaut | Description |
|---|---|---|---|
| `query` | string | requis | Question en langage naturel |
| `top_k` | int | 5 | Nombre de chunks retournés |
| `min_score` | float | 0.7 | Seuil de similarité minimum |
| `workspace(s)` | string / array | requis | Un ou plusieurs workspaces |

---

## Configuration côté client

Le fichier `.rag-client.json` à la racine du projet local ou du container :

```json
{
  "service": "https://rag.yoops.org/mcp",
  "workspaces": [
    { "name": "harpocrate",     "api_key": "ws_aaa..." },
    { "name": "ag-flow-docker", "api_key": "ws_bbb..." },
    { "name": "colis21",        "api_key": "ws_ccc..." }
  ]
}
```

Claude Code lit ce fichier et sait quel endpoint appeler et quels workspaces sont disponibles.

---

## Déclaration dans CLAUDE.md

```markdown
## RAG Service
config: .rag-client.json
outil MCP disponible: rag_search

Workspaces disponibles:
- harpocrate    — wiki et spec du secrets manager
- ag-flow-docker — doc et code du service Docker ag.flow
- colis21       — specs Pickup (lecture seule)

Usage: appeler rag_search(query, workspaces=[...]) pour enrichir le contexte
avant de répondre sur un sujet couvert par ces corpus.
```
