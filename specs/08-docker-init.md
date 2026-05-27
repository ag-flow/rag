# RAG Service — Init Docker

## Rôle

Quand un container agent ag.flow démarre, il doit provisionner sa configuration MCP locale en récupérant les api_keys des workspaces dont il a besoin. Ce provisioning est géré par un script d'init exécuté au démarrage du container.

---

## Variables d'environnement requises

Déclarées dans le `docker-compose.yml` ou la Swarm stack du projet :

```yaml
services:
  agent-docker:
    environment:
      RAG_SERVICE_URL: "https://rag.yoops.org"
      RAG_MASTER_KEY: "${RAG_MASTER_KEY}"
      RAG_WORKSPACES: '["harpocrate", "ag-flow-docker", "colis21"]'
```

`RAG_WORKSPACES` est une liste JSON — l'agent n'est pas verrouillé sur un seul workspace.

---

## Script d'init

```bash
#!/bin/bash
# init-rag.sh — exécuté dans l'entrypoint du container

set -e

RAG_CLIENT_FILE="/app/.rag-client.json"

echo '{"service": "'$RAG_SERVICE_URL'/mcp", "workspaces": []}' > $RAG_CLIENT_FILE

for workspace in $(echo $RAG_WORKSPACES | jq -r '.[]'); do
  echo "Provisioning RAG workspace: $workspace"

  # L'endpoint est protégé par Authorization: Bearer $RAG_MASTER_KEY
  response=$(curl -sf \
    -H "Authorization: Bearer $RAG_MASTER_KEY" \
    "$RAG_SERVICE_URL/api/admin/workspaces/$workspace/apikey")

  if [ $? -ne 0 ]; then
    echo "Warning: workspace '$workspace' not found or unreachable, skipping"
    continue
  fi

  api_key=$(echo $response | jq -r '.api_key')

  # Ajouter le workspace au fichier client
  tmp=$(jq --arg name "$workspace" --arg key "$api_key" \
    '.workspaces += [{"name": $name, "api_key": $key}]' \
    $RAG_CLIENT_FILE)
  echo $tmp > $RAG_CLIENT_FILE
done

echo "RAG client configured: $(jq '.workspaces | length' $RAG_CLIENT_FILE) workspace(s)"
```

---

## Résultat généré

```json
// /app/.rag-client.json
{
  "service": "https://rag.yoops.org/mcp",
  "workspaces": [
    { "name": "harpocrate",     "api_key": "ws_aaa..." },
    { "name": "ag-flow-docker", "api_key": "ws_bbb..." },
    { "name": "colis21",        "api_key": "ws_ccc..." }
  ]
}
```

---

## Idempotence

Le script est idempotent — le container peut redémarrer sans effet de bord. L'endpoint `GET /api/admin/workspaces/{name}/apikey` retourne toujours la même clé pour un workspace donné : côté serveur, la valeur est stockée sous forme chiffrée (`pgp_sym_encrypt`) et déchiffrée à la lecture grâce au secret `RAG_API_KEY_DEK`. Ce secret doit être défini dans le `.env` du backend avant le premier appel.

---

## Intégration dans l'entrypoint

```dockerfile
# Dockerfile agent
COPY init-rag.sh /app/init-rag.sh
RUN chmod +x /app/init-rag.sh

ENTRYPOINT ["/bin/bash", "-c", "/app/init-rag.sh && exec python main.py"]
```

---

## Prérequis serveur

Le service RAG doit avoir `RAG_API_KEY_DEK` défini (≥32 chars). Cette clé
maître chiffre les api_keys workspace en BDD et permet à l'endpoint
`GET /apikey` de fonctionner de manière idempotente. Cf. M5e dans
`docs/superpowers/specs/`.

---

## Utilisation par l'agent au runtime

L'agent lit `.rag-client.json` pour savoir quels workspaces sont disponibles et appelle le MCP en conséquence. Il choisit le ou les workspaces pertinents selon le contexte de la tâche — pas de workspace hardcodé dans le code agent.

```python
# Exemple agent — sélection dynamique des workspaces
rag_config = load_rag_client()  # lit .rag-client.json

# Pour une question sur l'architecture Harpocrate
results = rag_search(
    query="comment fonctionne la réplication MQTT ?",
    workspaces=["harpocrate"],
    config=rag_config
)

# Pour une question transverse
results = rag_search(
    query="comment les secrets sont gérés dans les containers ?",
    workspaces=["harpocrate", "ag-flow-docker"],
    config=rag_config
)
```
