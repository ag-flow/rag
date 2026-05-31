# 12 — Initialisation des agents Docker

Ce guide décrit comment les containers agents ag.flow se connectent automatiquement au service RAG au démarrage, sans configuration manuelle de chaque agent.

---

## Principe

Quand un container agent ag.flow démarre, un script d'initialisation (`init-rag.sh`) :
1. Appelle l'API admin du service RAG pour récupérer les clés API de chaque workspace
2. Génère un fichier `.rag-client.json` dans le container
3. L'agent lit ce fichier au runtime pour savoir quels workspaces interroger

```
Container agent (démarrage)
        │
        ▼
init-rag.sh
        │
        ├── GET /api/admin/workspaces/harpocrate/apikey      → ws_aaa...
        ├── GET /api/admin/workspaces/ag-flow-docker/apikey  → ws_bbb...
        └── GET /api/admin/workspaces/colis21/apikey         → ws_ccc...
        │
        ▼
/app/.rag-client.json (généré)
{
  "service": "https://rag.yoops.org/mcp",
  "workspaces": [
    { "name": "harpocrate",     "api_key": "ws_aaa..." },
    { "name": "ag-flow-docker", "api_key": "ws_bbb..." },
    { "name": "colis21",        "api_key": "ws_ccc..." }
  ]
}
        │
        ▼
Agent démarre → lit .rag-client.json → interroge le MCP au besoin
```

---

## Variables d'environnement requises dans le container agent

```yaml
# docker-compose.yml de votre projet agent
services:
  agent-docker:
    environment:
      RAG_SERVICE_URL: "https://rag.votre-domaine.fr"
      RAG_MASTER_KEY: "${RAG_MASTER_KEY}"
      RAG_WORKSPACES: '["harpocrate", "ag-flow-docker", "colis21"]'
```

| Variable | Description | Exemple |
|---|---|---|
| `RAG_SERVICE_URL` | URL publique du service RAG (sans slash final) | `https://rag.votre-domaine.fr` |
| `RAG_MASTER_KEY` | Master key du service RAG (même valeur que dans le `.env` du service) | `mk_xxx...` |
| `RAG_WORKSPACES` | Liste JSON des workspaces à provisionner | `'["harpocrate", "docs"]'` |

> **Sécurité :** `RAG_MASTER_KEY` doit être injectée via un secret Docker/Swarm, jamais hardcodée dans le `docker-compose.yml` versionné. Utilisez la syntaxe `${RAG_MASTER_KEY}` avec un `.env` local ou un gestionnaire de secrets.

---

## Script d'initialisation

Intégrez ce script dans votre Dockerfile agent :

```bash
#!/bin/bash
# init-rag.sh — exécuté dans l'entrypoint du container agent

set -e

RAG_CLIENT_FILE="/app/.rag-client.json"

# Initialiser le fichier avec l'URL du service
echo '{"service": "'"$RAG_SERVICE_URL"'/mcp", "workspaces": []}' > "$RAG_CLIENT_FILE"

# Provisionner chaque workspace
for workspace in $(echo "$RAG_WORKSPACES" | jq -r '.[]'); do
  echo "Provisioning RAG workspace: $workspace"

  response=$(curl -sf \
    -H "Authorization: Bearer $RAG_MASTER_KEY" \
    "$RAG_SERVICE_URL/api/admin/workspaces/$workspace/apikey")

  if [ $? -ne 0 ]; then
    echo "Warning: workspace '$workspace' not found or unreachable, skipping"
    continue
  fi

  api_key=$(echo "$response" | jq -r '.api_key')

  # Ajouter ce workspace à la config
  tmp=$(jq \
    --arg name "$workspace" \
    --arg key "$api_key" \
    '.workspaces += [{"name": $name, "api_key": $key}]' \
    "$RAG_CLIENT_FILE")
  echo "$tmp" > "$RAG_CLIENT_FILE"
done

count=$(jq '.workspaces | length' "$RAG_CLIENT_FILE")
echo "RAG client configured: $count workspace(s)"
```

### Intégration dans le Dockerfile

```dockerfile
# Dockerfile de votre agent
FROM python:3.12-slim

# ... autres instructions ...

COPY init-rag.sh /app/init-rag.sh
RUN chmod +x /app/init-rag.sh

# Le script init-rag.sh s'exécute avant l'agent
ENTRYPOINT ["/bin/bash", "-c", "/app/init-rag.sh && exec python main.py"]
```

---

## Fichier `.rag-client.json` généré

```json
{
  "service": "https://rag.votre-domaine.fr/mcp",
  "workspaces": [
    { "name": "harpocrate",     "api_key": "ws_aaa111bbb222ccc333" },
    { "name": "ag-flow-docker", "api_key": "ws_ddd444eee555fff666" },
    { "name": "colis21",        "api_key": "ws_ggg777hhh888iii999" }
  ]
}
```

> **Note :** Ce fichier contient des clés API en clair dans le container. Ne l'incluez jamais dans une image Docker ou dans un volume persistant non sécurisé. Il doit être généré à chaque démarrage et exister uniquement en mémoire du container.

---

## Utilisation par l'agent au runtime

L'agent lit `.rag-client.json` pour sélectionner dynamiquement les workspaces pertinents selon le contexte de la tâche :

```python
import json
from pathlib import Path

def load_rag_client() -> dict:
    """Charge la configuration RAG générée par init-rag.sh."""
    client_file = Path("/app/.rag-client.json")
    if not client_file.exists():
        return {"service": None, "workspaces": []}
    return json.loads(client_file.read_text())

def get_workspace_api_key(workspace_name: str) -> str | None:
    """Retourne la clé API d'un workspace par son nom."""
    config = load_rag_client()
    for ws in config["workspaces"]:
        if ws["name"] == workspace_name:
            return ws["api_key"]
    return None
```

```python
# Exemple d'utilisation — recherche ciblée sur un workspace
import httpx

rag_config = load_rag_client()
api_key = get_workspace_api_key("harpocrate")

# Appel MCP REST (ancien endpoint)
response = httpx.post(
    f"{rag_config['service']}",
    json={
        "workspace": "harpocrate",
        "api_key": api_key,
        "query": "comment fonctionne la réplication MQTT ?",
        "top_k": 5,
        "min_score": 0.3
    }
)
results = response.json()["results"]
```

```python
# Exemple — recherche multi-workspaces (plusieurs corpus)
response = httpx.post(
    f"{rag_config['service']}",
    json={
        "workspaces": [
            {"name": "harpocrate", "api_key": get_workspace_api_key("harpocrate")},
            {"name": "ag-flow-docker", "api_key": get_workspace_api_key("ag-flow-docker")}
        ],
        "query": "comment les secrets sont gérés dans les containers ?",
        "top_k": 10,
        "min_score": 0.3
    }
)
```

---

## Configuration pour Claude Code dans un container

Si votre container inclut Claude Code, configurez le fichier `~/.claude/mcp.json` dans le container pour pointer vers le service RAG :

```bash
# Dans init-rag.sh, après la génération de .rag-client.json

CLAUDE_MCP_DIR="$HOME/.claude"
mkdir -p "$CLAUDE_MCP_DIR"

# Générer la config MCP Claude Code pour chaque workspace
mcp_config="{\"mcpServers\": {}}"

for workspace in $(echo "$RAG_WORKSPACES" | jq -r '.[]'); do
  ws_id=$(curl -sf \
    -H "Authorization: Bearer $RAG_MASTER_KEY" \
    "$RAG_SERVICE_URL/api/admin/workspaces/$workspace" \
    | jq -r '.id')
  api_key=$(jq -r --arg ws "$workspace" \
    '.workspaces[] | select(.name==$ws) | .api_key' \
    /app/.rag-client.json)

  mcp_config=$(echo "$mcp_config" | jq \
    --arg name "$workspace" \
    --arg url "$RAG_SERVICE_URL/mcp/$ws_id" \
    --arg key "$api_key" \
    '.mcpServers[$name] = {"url": $url, "headers": {"Authorization": ("Bearer " + $key)}}')
done

echo "$mcp_config" > "$CLAUDE_MCP_DIR/mcp.json"
echo "Claude Code MCP config generated"
```

---

## Idempotence

Le script `init-rag.sh` est **idempotent** : le container peut redémarrer autant de fois que nécessaire. L'endpoint `GET /api/admin/workspaces/{name}/apikey` retourne toujours la même clé active pour un workspace donné (la première clé non révoquée).

---

## Dépannage

### "workspace not found or unreachable"

- Vérifiez que `RAG_SERVICE_URL` est correct et accessible depuis le container
- Vérifiez que le workspace existe : `curl -H "Authorization: Bearer $RAG_MASTER_KEY" $RAG_SERVICE_URL/api/admin/workspaces`
- Vérifiez que `RAG_MASTER_KEY` est correctement défini

### Le container démarre mais l'agent ne trouve pas de résultats

- Vérifiez que des sources git sont configurées sur le workspace
- Vérifiez que des jobs d'indexation ont réussi (onglet Jobs dans l'interface)
- Essayez de réduire `min_score` à 0.2

### Clé API expirée

Les clés API workspace n'expirent pas automatiquement (sauf rotation ou révocation manuelle). Si une clé est révoquée, re-démarrez le container pour en récupérer une nouvelle via `init-rag.sh`.

---

## Prochaine étape

→ [13 — Déduplication](13-deduplication.md)
