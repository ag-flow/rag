# RAG Service — API Workspace

## Authentification

Ces endpoints utilisent l'**api_key workspace** (pas la master key) :

```
Authorization: Bearer {WORKSPACE_API_KEY}
```

L'api_key est obtenue via `GET /workspaces/{name}/apikey` avec la master key. Voir `02-api-admin.md` et `08-docker-init.md`.

---

## Indexation à la demande (push asynchrone)

```
POST /workspaces/{name}/index
```

Permet à un agent de soumettre un document pour indexation. Le service enregistre la demande, rend la main immédiatement avec un `X-Correlation-ID`, et traite l'indexation en arrière-plan.

### Requête

```json
{
  "path": "generated/docker-analysis.md",
  "content": "# Analyse Docker\n\nContenu du document..."
}
```

### Comportement

1. Enregistre le job en base (`status: pending`)
2. Génère un `X-Correlation-ID` (UUID)
3. Retourne `202 Accepted` immédiatement

En arrière-plan :
4. Calcule `SHA-256(content)`
5. Compare avec le hash stocké dans `indexed_documents`
6. Si identique → job `status: skipped`, webhooks notifiés
7. Si différent → chunk + embed + upsert pgvector → job `status: done`, webhooks notifiés

### Réponse `202 Accepted`

```http
HTTP/1.1 202 Accepted
X-Correlation-ID: 7f3a1b2c-9e4d-4f8a-b1c2-3d4e5f6a7b8c

{
  "job_id": "uuid...",
  "status": "pending"
}
```

Le donneur d'ordre conserve le `X-Correlation-ID` pour corréler avec le webhook entrant à la fin du traitement.

### Usage typique dans un agent ag.flow

```bash
# L'agent soumet le fichier pour indexation
response=$(curl -si -X POST "$RAG_SERVICE/workspaces/harpocrate/index" \
  -H "Authorization: Bearer $WS_API_KEY_HARPOCRATE" \
  -H "Content-Type: application/json" \
  -d "{
    \"path\": \"generated/docker-analysis.md\",
    \"content\": \"$(cat ./generated/docker-analysis.md | jq -Rs .)\"
  }")

# 202 reçu → demande enregistrée
# Extraire le correlation ID pour tracer le webhook entrant
correlation_id=$(echo "$response" | grep -i "X-Correlation-ID" | awk '{print $2}')

# Le webhook arrivera avec le même X-Correlation-ID quand l'indexation sera terminée
```

---

## Notes

- Le `path` est la clé d'upsert — indexer un document déjà existant le remplace
- Le contenu des chunks est conservé en base pour être retourné dans les résultats MCP
- L'indexation push et l'indexation git utilisent le même moteur — même déduplication par hash
- Le `X-Correlation-ID` est généré par le service — le client ne peut pas le fixer
- Le webhook est envoyé dans tous les cas — `done`, `skipped` ou `error`
