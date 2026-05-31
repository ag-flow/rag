# Design — Serveur MCP standard (Streamable HTTP)

**Date :** 2026-05-31
**Statut :** validé

## Contexte

Le service RAG expose actuellement un endpoint REST custom `POST /mcp`. Ce chantier ajoute un vrai serveur **Model Context Protocol** (Anthropic) en transport Streamable HTTP, permettant à Claude Code de consommer le RAG comme un serveur MCP natif sans aucun wrapper local.

Le service est open source et auto-hébergeable : l'URL est entièrement configurable.

---

## Section 1 — Transport & Endpoint

### URL

```
/mcp/{workspace_id}
```

`workspace_id` = UUID du workspace (champ `workspaces.id` existant en base).

Le SDK MCP Python (`mcp`) expose une classe `Server` montée comme sous-app ASGI dans FastAPI :

```python
app.mount("/mcp/{workspace_id}", mcp_asgi_app)
```

### Configuration Claude Code

```json
{
  "mcpServers": {
    "mon-rag": {
      "url": "http://rag.yoops.org/mcp/550e8400-e29b-41d4-a716-446655440000",
      "headers": {
        "Authorization": "Bearer ws_xxx..."
      }
    }
  }
}
```

Deux paramètres distincts :
- **URL** : identifie le workspace (GUID dans le path)
- **Header Authorization** : authentifie l'appelant (une des `workspace_api_keys`)

---

## Section 2 — Outil exposé

### `rag_search`

Un seul outil. Le workspace est implicite (dans l'URL), pas dans les paramètres.

```
rag_search(
  query:     string   — requis, question en langage naturel
  top_k:     integer  — optionnel, défaut 5, max 50
  min_score: number   — optionnel, défaut 0.3
)
→ list[{ path, chunk_index, content, score }]
```

### Handshake `initialize`

```json
{
  "name": "rag-{workspace_name}",
  "version": "1.0",
  "capabilities": { "tools": {} }
}
```

Le nom inclut le `workspace_name` pour que Claude Code distingue plusieurs serveurs RAG configurés en parallèle.

### Format de réponse

Chaque chunk est sérialisé en texte Markdown injecté dans le contexte Claude Code :

```
[path/to/file.md — chunk 2 — score 0.87]
Le contenu du chunk ici...

[autre/fichier.md — chunk 0 — score 0.81]
...
```

---

## Section 3 — Authentification

À chaque appel MCP :

1. Extraire `workspace_id` du path ASGI
2. Extraire le token du header `Authorization: Bearer {token}`
3. Calculer `fingerprint = SHA-256(token)`
4. Lookup DB :
   ```sql
   SELECT w.id, w.name, k.api_key_ref
   FROM workspaces w
   JOIN workspace_api_keys k ON k.workspace_id = w.id
   WHERE w.id = $1
     AND k.fingerprint = $2
     AND k.revoked_at IS NULL
     AND (k.rotated_at IS NULL OR k.rotated_at > now() - interval '72 hours')
   ```
5. Résoudre `api_key_ref` via `ApiKeyCache` (puis Harpocrate sur miss)
6. `compare_digest(cached, token)` — timing-safe

Erreurs :
- workspace_id inconnu → `404 Not Found` HTTP (avant même le handshake MCP)
- token invalide → erreur MCP `-32001 Unauthorized`

La logique réutilise `services/mcp.py::_authenticate` — pas de duplication.

---

## Section 4 — Onglet "Api"

### Renommage

L'onglet **"API Keys"** devient **"Api"** dans `WorkspaceDetailPanel`.

### Contenu

Section **Connexion MCP** ajoutée en haut de `WorkspaceApiKeysTab` :

- **URL MCP** : `{RAG_PUBLIC_URL}/mcp/{workspace.id}` — champ read-only + bouton copie
- **Config Claude Code** : bloc JSON prêt à coller dans `.claude/mcp.json`, avec l'URL pré-remplie et `"Authorization": "Bearer <votre-clé>"` comme placeholder — bouton copie

`RAG_PUBLIC_URL` vient de `import.meta.env.VITE_PUBLIC_URL` ; fallback `window.location.origin` si absent.

Le tableau des clés API existant reste en dessous, inchangé.

---

## Périmètre hors-scope

- Support multi-workspace dans un seul serveur MCP (un endpoint = un workspace)
- OAuth / PKCE (auth via header Bearer suffit)
- Outil supplémentaire `rag_index` (push de document via MCP)
- Évolution future : token encodé portant workspace_id + auth en une seule chaîne
