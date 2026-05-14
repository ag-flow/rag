# RAG Service — API Workspace

## Authentification

Ces endpoints utilisent l'**api_key workspace** (pas la master key) :

```
Authorization: Bearer {WORKSPACE_API_KEY}
```

L'api_key est obtenue via `GET /workspaces/{name}/apikey` avec la master key. Voir `02-api-admin.md` et `08-docker-init.md`.

---

## Indexation à la demande (push synchrone)

```
POST /workspaces/{name}/index
```

Permet à un agent de pousser un document et de l'indexer immédiatement, sans attendre un commit git.

### Requête

```json
{
  "path": "generated/docker-analysis.md",
  "content": "# Analyse Docker\n\nContenu du document..."
}
```

### Comportement

1. Calcule `SHA-256(content)`
2. Compare avec le hash stocké dans `indexed_documents`
3. Si identique → `200 OK` immédiat, zéro appel embedding
4. Si différent → chunk + embed + upsert pgvector → met à jour le hash → `200 OK`

L'endpoint est **bloquant** — le client attend la fin de l'indexation avant de recevoir la réponse.

### Réponse `200 OK`

```json
{
  "path": "generated/docker-analysis.md",
  "status": "indexed",
  "chunks": 4,
  "hash": "sha256:abc123..."
}
```

### Réponse `200 OK` (dédupliqué)

```json
{
  "path": "generated/docker-analysis.md",
  "status": "skipped",
  "reason": "content_unchanged"
}
```

### Usage typique dans un agent ag.flow

```bash
# L'agent génère un fichier, puis l'indexe immédiatement
curl -X POST "$RAG_SERVICE/workspaces/harpocrate/index" \
  -H "Authorization: Bearer $WS_API_KEY_HARPOCRATE" \
  -H "Content-Type: application/json" \
  -d "{
    \"path\": \"generated/docker-analysis.md\",
    \"content\": \"$(cat ./generated/docker-analysis.md | jq -Rs .)\"
  }"

# 200 reçu → document searchable immédiatement via MCP
```

---

## Notes

- Le `path` est la clé d'upsert — indexer un document déjà existant le remplace
- Le contenu des chunks est conservé en base pour être retourné dans les résultats MCP
- L'indexation push et l'indexation git utilisent le même moteur — même déduplication par hash
