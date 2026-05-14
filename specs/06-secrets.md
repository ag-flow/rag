# RAG Service — Gestion des Secrets

## Principe

Le service RAG ne stocke jamais de secret en clair — ni en base, ni dans les logs, ni dans les fichiers de config commitées. Tous les secrets sont référencés par une **clé logique opaque** et résolus au runtime via Harpocrate.

---

## Modèle de référence

Une `api_key_ref` est une clé logique stable qui pointe vers un secret dans Harpocrate :

```
"openai_embedding_key"   ←  clé logique (stockée en base RAG)
        │
        ▼
Harpocrate : lookup("openai_embedding_key")
        │
        ▼
hash_abc123 → /openai/text_embedding  ←  path physique (géré par Harpocrate)
        │
        ▼
"sk-xxx..."  ←  valeur réelle (jamais vue par le service RAG)
```

Le service RAG ne connaît jamais le path physique — uniquement la clé logique. Si Harpocrate déplace le secret, la clé logique reste valide sans aucune modification côté RAG.

---

## Secrets gérés

| Clé logique | Usage |
|---|---|
| `openai_embedding_key` | API key OpenAI embeddings |
| `voyage_api_key` | API key Voyage AI |
| `github_token` | Auth sources git GitHub |
| `azure_devops_token` | Auth sources git Azure DevOps |

---

## Amorçage du service (phase 1)

Le seul secret d'amorçage est la connexion à Harpocrate, stockée dans le `.env` :

```env
HARPOCRATE_URL=https://harpocrate.yoops.org
HARPOCRATE_TOKEN=harp_xxx
RAG_MASTER_KEY=mk_xxx
```

Le `HARPOCRATE_TOKEN` permet au service RAG d'appeler l'API Harpocrate pour résoudre les secrets. La sécurisation de ce token en phase 2 est gérée par le SDK Harpocrate — transparent pour le service RAG.

---

## Résolution au runtime

Le `SecretResolver` est appelé à chaque utilisation d'un secret (pas au démarrage) :

```python
class SecretResolver:

    def resolve(self, ref: str) -> str:
        """
        Résout une clé logique vers la valeur du secret.
        ref: clé logique, ex: "openai_embedding_key"
        Retourne la valeur en clair en mémoire uniquement.
        """
        response = httpx.get(
            f"{HARPOCRATE_URL}/secrets/lookup/{ref}",
            headers={"Authorization": f"Bearer {HARPOCRATE_TOKEN}"},
            timeout=5.0
        )
        response.raise_for_status()
        return response.json()["value"]
```

La valeur résolue est utilisée immédiatement et n'est jamais persistée.

---

## Ce qui est stocké en base

```sql
-- indexer_configs
api_key_ref = 'openai_embedding_key'   -- clé logique uniquement

-- workspace_sources.config (jsonb)
{ "auth_ref": "github_token", ... }    -- clé logique uniquement
```

Aucun secret, aucun hash de secret, aucune valeur chiffrée — uniquement des identifiants logiques opaques.

---

## Phase 2 — SDK Harpocrate

La sécurisation du `HARPOCRATE_TOKEN` dans le `.env` sera gérée par le SDK Harpocrate (écriture chiffrée, déchiffrement au runtime). Aucun changement requis côté service RAG — transparent par conception.
