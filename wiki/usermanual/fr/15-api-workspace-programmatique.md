# 15 — API Workspace — Guide programmatique

Ce guide s'adresse aux développeurs qui intègrent le service RAG dans une application ou un agent, via l'API REST directement (sans passer par le protocole MCP).

---

## Deux modes d'indexation

Le service offre deux modes pour indexer un document à la demande :

| Mode | Endpoint | Comportement | Usage |
|---|---|---|---|
| **Synchrone** | `POST /workspaces/{name}/index` | Bloquant — attend la fin de l'indexation | Agents qui ont besoin que le document soit immédiatement searchable |
| **Asynchrone** | `POST /workspaces/{name}/index` (avec `async=true`) | Non bloquant — retourne `202 Accepted` immédiatement | Pipelines de traitement batch |

> **Note :** L'endpoint actuel fonctionne en mode **synchrone** par défaut. Le client attend la réponse `200 OK` avant de continuer.

---

## Authentification

L'API workspace utilise la **clé API workspace** (pas la master key) :

```bash
# Obtenir la clé API du workspace (via master key, une seule fois)
export WORKSPACE_API_KEY=$(curl -sf \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  "https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/apikey" \
  | jq -r '.api_key')
```

Utilisez cette clé pour tous les appels workspace :
```bash
Authorization: Bearer $WORKSPACE_API_KEY
```

---

## Indexation d'un document

### Requête

```bash
curl -X POST "https://rag.votre-domaine.fr/workspaces/mon-projet/index" \
  -H "Authorization: Bearer $WORKSPACE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "path": "generated/analyse-docker.md",
    "content": "# Analyse Docker\n\nLe container utilise une image alpine..."
  }'
```

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| `path` | string | Oui | Chemin relatif du document (clé d'upsert) |
| `content` | string | Oui | Contenu textuel complet du document |

### Réponses

**Document indexé (nouveau ou modifié) :**
```json
{
  "path": "generated/analyse-docker.md",
  "status": "indexed",
  "chunks": 4,
  "hash": "sha256:a3f2c1d4e5b6..."
}
```

**Document inchangé (déduplication) :**
```json
{
  "path": "generated/analyse-docker.md",
  "status": "skipped",
  "reason": "content_unchanged"
}
```

### Gestion des erreurs

```bash
# 401 — Clé API invalide ou révoquée
{"detail": "invalid_workspace_apikey"}

# 404 — Workspace introuvable
{"detail": "workspace not found"}

# 422 — Paramètre manquant
{"detail": [{"loc": ["body", "path"], "msg": "field required"}]}
```

---

## Intégration dans un agent Python

### Classe client réutilisable

```python
import hashlib
import httpx
from pathlib import Path


class RagClient:
    """Client pour l'API workspace RAG."""

    def __init__(self, base_url: str, workspace: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.workspace = workspace
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60.0,  # 60s pour les gros documents
        )

    async def index(self, path: str, content: str) -> dict:
        """Indexe un document. Retourne le statut (indexed/skipped)."""
        response = await self._client.post(
            f"{self.base_url}/workspaces/{self.workspace}/index",
            json={"path": path, "content": content},
        )
        response.raise_for_status()
        return response.json()

    async def index_file(self, file_path: Path, rag_path: str | None = None) -> dict:
        """Indexe un fichier local. rag_path = chemin dans le corpus RAG."""
        content = file_path.read_text(encoding="utf-8")
        path = rag_path or str(file_path)
        return await self.index(path, content)

    async def close(self) -> None:
        await self._client.aclose()


# Utilisation
async def main():
    rag = RagClient(
        base_url="https://rag.votre-domaine.fr",
        workspace="mon-projet",
        api_key="ws_votre_cle_api",
    )

    # Indexer un fichier généré
    result = await rag.index(
        path="generated/rapport-2026-05-31.md",
        content="# Rapport\n\nAnalyse complète..."
    )

    if result["status"] == "indexed":
        print(f"Indexé en {result['chunks']} chunks")
    else:
        print("Contenu inchangé, skip")

    await rag.close()
```

---

## Corrélation avec les webhooks sortants

Si votre workspace a des webhooks sortants configurés, vous pouvez corréler votre push avec la notification reçue via le `X-Correlation-ID` :

```python
import httpx

async def index_and_wait_webhook(
    rag_url: str,
    workspace: str,
    api_key: str,
    path: str,
    content: str,
) -> str:
    """Indexe un document et retourne le correlation ID pour tracer le webhook."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{rag_url}/workspaces/{workspace}/index",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"path": path, "content": content},
        )
        response.raise_for_status()

        # Le correlation ID est dans les headers de la réponse
        correlation_id = response.headers.get("X-Correlation-ID")
        return correlation_id

# Votre webhook entrant recevra ce même correlation_id dans ses headers :
# POST https://votre-serveur.fr/hooks/rag
# X-Correlation-ID: 7f3a1b2c-9e4d-...
```

---

## Indexation batch

Pour indexer plusieurs documents en parallèle :

```python
import asyncio
from pathlib import Path


async def index_directory(
    rag: RagClient,
    directory: Path,
    pattern: str = "**/*.md",
    prefix: str = "",
) -> dict:
    """Indexe tous les fichiers correspondant au pattern dans un répertoire."""
    files = list(directory.glob(pattern))

    results = {"indexed": 0, "skipped": 0, "errors": 0}

    # Indexer par batches de 10 pour éviter la surcharge
    batch_size = 10
    for i in range(0, len(files), batch_size):
        batch = files[i : i + batch_size]
        tasks = [
            rag.index_file(
                file_path=f,
                rag_path=f"{prefix}/{f.relative_to(directory)}" if prefix else str(f.relative_to(directory))
            )
            for f in batch
        ]

        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in batch_results:
            if isinstance(result, Exception):
                results["errors"] += 1
                print(f"Erreur: {result}")
            elif result["status"] == "indexed":
                results["indexed"] += 1
            else:
                results["skipped"] += 1

    return results


# Utilisation
async def main():
    rag = RagClient("https://rag.votre-domaine.fr", "mon-projet", "ws_cle")

    stats = await index_directory(
        rag=rag,
        directory=Path("./generated"),
        pattern="**/*.md",
        prefix="generated",
    )

    print(f"Indexé: {stats['indexed']}, Skippé: {stats['skipped']}, Erreurs: {stats['errors']}")
    await rag.close()
```

---

## Intégration dans un workflow CI/CD

### GitHub Actions

```yaml
# .github/workflows/index-rag.yml
name: Index documentation in RAG

on:
  push:
    branches: [main]
    paths:
      - 'docs/**'
      - 'generated/**'

jobs:
  index:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Index modified files in RAG
        env:
          RAG_URL: ${{ secrets.RAG_URL }}
          RAG_WORKSPACE_API_KEY: ${{ secrets.RAG_WORKSPACE_API_KEY }}
        run: |
          # Récupérer les fichiers modifiés
          CHANGED=$(git diff --name-only HEAD~1 HEAD -- 'docs/*.md' 'generated/*.md')

          for file in $CHANGED; do
            if [ -f "$file" ]; then
              content=$(cat "$file" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
              response=$(curl -sf -X POST "$RAG_URL/workspaces/mon-projet/index" \
                -H "Authorization: Bearer $RAG_WORKSPACE_API_KEY" \
                -H "Content-Type: application/json" \
                -d "{\"path\": \"$file\", \"content\": $content}")
              status=$(echo $response | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
              echo "$file → $status"
            fi
          done
```

---

## Bonnes pratiques

### Gestion du chemin (`path`)

Le `path` est la **clé d'upsert** dans le corpus RAG. Choisissez une convention cohérente :

```python
# Bon — chemin relatif et lisible
"path": "src/UserService.py"
"path": "docs/architecture/replication.md"
"path": "generated/analyse-2026-05-31.md"

# À éviter — chemin absolu (non portable)
"path": "/home/user/projects/app/src/UserService.py"
```

### Taille des documents

L'API n'a pas de limite stricte, mais :
- **Recommandé :** documents ≤ 50 000 caractères (~50 Ko de texte)
- Au-delà, le chunking produit de nombreux chunks et ralentit l'indexation
- Pour les très gros fichiers, envisagez de les découper avant indexation

### Retry en cas d'erreur

```python
import asyncio
import httpx

async def index_with_retry(
    rag: RagClient,
    path: str,
    content: str,
    max_retries: int = 3,
) -> dict:
    """Indexe avec retry exponentiel en cas d'erreur temporaire."""
    for attempt in range(max_retries):
        try:
            return await rag.index(path, content)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 503) and attempt < max_retries - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s
                await asyncio.sleep(wait)
                continue
            raise
    raise RuntimeError(f"Échec après {max_retries} tentatives")
```

### Sécurité de la clé API

- Ne jamais logguer la clé API workspace
- Stocker dans les secrets CI/CD (GitHub Secrets, etc.), pas en dur dans le code
- Utilisez des clés nommées distinctes par service/agent pour faciliter la révocation

---

## Prochaine étape

→ [16 — Gestion des credentials dans les coffres](16-credentials-coffres.md)
