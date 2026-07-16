# 12 — Initialisation des agents Docker

Ce guide décrit comment les containers agents ag.flow se connectent au service RAG au démarrage, sans configuration manuelle de chaque agent.

---

## Principe

L'agent reçoit une **clé API utilisateur pré-provisionnée** via variable d'environnement. Cette clé, créée une fois dans l'IHM (**Configuration → Clés API**), porte les **grants** vers les workspaces que l'agent doit atteindre :

- **READ** — recherche sémantique via MCP
- **WRITE** — indexation push (si l'agent produit des documents)

> **Changement de modèle :** les clés ne sont plus récupérables via l'API
> (`GET /workspaces/{name}/apikey` n'existe plus). La valeur d'une clé n'est
> affichée qu'à sa création — seule son empreinte SHA-256 est stockée côté
> serveur. Le provisioning se fait donc **par injection**, pas par lecture.

```
Admin (une fois)                          Container agent (à chaque démarrage)
────────────────                          ────────────────────────────────────
IHM → Clés API → créer "agent-docker"     RAG_API_KEY=<valeur> (env/secret)
  ├─ grant workspace harpocrate  (R)              │
  ├─ grant workspace agflow-code (R)              ▼
  └─ grant workspace colis21     (R/W)    init-rag.sh génère .rag-client.json
  → copier la clé → secret Docker         + ~/.claude/mcp.json si Claude Code
```

---

## Variables d'environnement du container

```yaml
# docker-compose.yml de votre projet agent
services:
  agent-docker:
    environment:
      RAG_SERVICE_URL: "https://rag.votre-domaine.fr"
      RAG_API_KEY: "${RAG_AGENT_API_KEY}"          # clé utilisateur pré-provisionnée
      RAG_WORKSPACES: '["harpocrate", "agflow-code", "colis21"]'
```

| Variable | Description |
|---|---|
| `RAG_SERVICE_URL` | URL publique du service RAG (sans slash final) |
| `RAG_API_KEY` | Clé API utilisateur (injectée via secret Docker/Swarm, jamais versionnée) |
| `RAG_WORKSPACES` | Liste JSON des noms de workspaces que l'agent interroge |

> **Sécurité :** la clé donne exactement les accès de ses grants — préférez une
> clé dédiée par agent (révocation ciblée), avec READ seul si l'agent ne pousse
> pas de documents. Plus de master key dans les containers agents.

---

## Script d'initialisation

```bash
#!/bin/bash
# init-rag.sh — exécuté dans l'entrypoint du container agent
set -e

RAG_CLIENT_FILE="/app/.rag-client.json"

jq -n --arg svc "$RAG_SERVICE_URL/mcp" --arg key "$RAG_API_KEY" \
  --argjson ws "$RAG_WORKSPACES" \
  '{service: $svc, api_key: $key, workspaces: $ws}' > "$RAG_CLIENT_FILE"

echo "RAG client configured: $(echo "$RAG_WORKSPACES" | jq 'length') workspace(s)"
```

```dockerfile
# Dockerfile de l'agent
COPY init-rag.sh /app/init-rag.sh
RUN chmod +x /app/init-rag.sh
ENTRYPOINT ["/bin/bash", "-c", "/app/init-rag.sh && exec python main.py"]
```

### Fichier `.rag-client.json` généré

```json
{
  "service": "https://rag.votre-domaine.fr/mcp",
  "api_key": "xxxxx",
  "workspaces": ["harpocrate", "agflow-code", "colis21"]
}
```

> Une seule clé pour tous les workspaces de l'agent — les droits par workspace
> sont portés par les grants côté serveur. Ne jamais inclure ce fichier dans
> une image ou un volume persistant.

---

## Configuration pour Claude Code dans un container

Pour chaque workspace, il faut son **UUID** (visible dans l'onglet Api du workspace, ou via `GET /api/admin/workspaces/{name}` si le pipeline d'infra dispose de la master key) :

```bash
# Dans init-rag.sh — RAG_WORKSPACE_IDS='{"harpocrate":"uuid1","agflow-code":"uuid2"}'
mkdir -p "$HOME/.claude"
jq -n --arg url "$RAG_SERVICE_URL" --arg key "$RAG_API_KEY" \
  --argjson ids "$RAG_WORKSPACE_IDS" \
  '{mcpServers: ($ids | to_entries | map({(.key): {url: ($url + "/mcp/" + .value), headers: {Authorization: ("Bearer " + $key)}}}) | add)}' \
  > "$HOME/.claude/mcp.json"
```

---

## Utilisation par l'agent au runtime

```python
import json
from pathlib import Path

import httpx


def load_rag_client() -> dict:
    f = Path("/app/.rag-client.json")
    return json.loads(f.read_text()) if f.exists() else {"service": None, "workspaces": []}


# Recherche sur un workspace (endpoint REST legacy /mcp)
cfg = load_rag_client()
response = httpx.post(
    cfg["service"],
    json={
        "workspace": "harpocrate",
        "api_key": cfg["api_key"],
        "query": "comment fonctionne la réplication MQTT ?",
        "top_k": 5,
        "min_score": 0.3,
    },
)
```

---

## Rotation et révocation

- **Rotation** (planifiée) : IHM → Clés API → rotation → mettre à jour le secret Docker. L'ancienne clé reste valide **72 h** — largement le temps de redéployer.
- **Révocation** (compromission) : IHM → Clés API → révoquer. Effet immédiat sur tous les workspaces de la clé.

---

## Dépannage

### 401 `invalid_workspace_apikey`

- La clé est révoquée/expirée, OU n'a pas de grant sur ce workspace, OU n'a pas la bonne **permission** (READ pour la recherche, WRITE pour le push).
- Vérifiez les grants dans **Configuration → Clés API**.

### L'agent ne trouve pas de résultats

- Vérifiez que des sources sont configurées et qu'un job d'indexation a réussi (onglet Jobs).
- Essayez `min_score` à 0.2.

---

## Prochaine étape

→ [13 — Déduplication](13-deduplication.md)
