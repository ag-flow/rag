# BUG-084 — Caddyfile prod : `handle /mcp` ne matche pas `/mcp/{workspace_id}` — endpoint MCP inaccessible via le proxy

**Statut : 🟢 corrigé**

- **Zone** : infra / deploy/prod/Caddyfile
- **Sévérité** : **critique**
- **Complexité** : simple
- **Fichiers** : `deploy/prod/Caddyfile:43-45`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Le backend monte le dispatcher MCP standard sur `/mcp` avec un segment workspace obligatoire (`app.mount("/mcp", ...)` + `_extract_workspace_id`). L'UI (`WorkspaceApiKeysTab.tsx:46` : `` `${publicUrl}/mcp/${workspaceId}` ``) et le wiki publient `https://…/mcp/{workspace_id}`. Or en Caddy, un path matcher sans `*` est un match **exact** : `handle /mcp` ne matche que `/mcp` pile, jamais `/mcp/<uuid>`.

## Scénario de défaillance

En prod (seul le port Caddy est exposé, backend:8000 n'est pas publié), un client MCP se connecte à l'URL affichée dans l'IHM → la requête `/mcp/<uuid>` tombe dans le `handle` catch-all → réponse `200 "ag-flow.rag — interface : /ui …"` en text/plain. Le client MCP échoue avec une erreur de parsing, le proxy renvoyant 200 rend le diagnostic très confus.

## Code concerné

```
    handle /mcp {
        reverse_proxy backend:8000
    }
```

## Piste de correction

Remplacer par `handle /mcp* { … }` (ou `handle /mcp/* + handle /mcp`).
