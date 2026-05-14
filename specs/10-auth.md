# RAG Service — Authentification

## Deux couches d'authentification

Le service RAG distingue deux types d'accès avec des mécanismes différents :

```
Humain via navigateur  →  OIDC Keycloak  →  IHM web
Agent / curl / MCP     →  Bearer token   →  API REST
```

Ces deux couches sont indépendantes — l'une n'interfère pas avec l'autre.

---

## Couche 1 — IHM web (OIDC)

### Principe

L'interface web de gestion des workspaces, sources et jobs est protégée par OpenID Connect via l'instance Keycloak du homelab.

### Configuration

Stockée en base `rag_config`, table `oidc_config` :

```sql
CREATE TABLE oidc_config (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  issuer              TEXT NOT NULL,
  client_id           TEXT NOT NULL,
  client_secret_ref   TEXT NOT NULL,   -- clé logique Harpocrate
  created_at          TIMESTAMPTZ DEFAULT now(),
  updated_at          TIMESTAMPTZ DEFAULT now()
);
```

Exemple de valeurs :

```json
{
  "issuer": "https://keycloak.yoops.org/realms/homelab",
  "client_id": "rag-service",
  "client_secret_ref": "keycloak_rag_client_secret"
}
```

Le `client_secret` est résolu via Harpocrate au démarrage — jamais stocké en clair. Voir `06-secrets.md`.

### Flow OIDC

```
Navigateur → GET /ui
      │
      ▼ (non authentifié)
Redirect → Keycloak /realms/homelab/protocol/openid-connect/auth
      │
      ▼ (login Keycloak)
Callback → /auth/callback?code=xxx
      │
      ▼
Échange code → token (via client_secret résolu depuis Harpocrate)
      │
      ▼
Session utilisateur créée
      │
      ▼
Accès IHM
```

### Rôles Keycloak

Deux rôles définis dans le realm Keycloak, côté client `rag-service` :

| Rôle | Accès |
|---|---|
| `rag-admin` | Lecture + écriture — gestion workspaces, sources, reindex |
| `rag-viewer` | Lecture seule — consultation workspaces, jobs, documents |

---

## Couche 2 — API REST et MCP (Bearer token)

Les appels machine utilisent des tokens opaques — OIDC n'est pas adapté aux appels programmatiques.

| Token | Portée | Obtenu via |
|---|---|---|
| `RAG_MASTER_KEY` | Administration complète | Défini dans `.env` au déploiement |
| `workspace api_key` | Usage d'un workspace (index + MCP) | `GET /workspaces/{name}/apikey` avec master key |

Ces tokens ne passent pas par Keycloak.

---

## Configuration dans le `.env`

```env
# Amorçage Keycloak (phase 1 — sera sécurisé par SDK Harpocrate en phase 2)
HARPOCRATE_URL=https://harpocrate.yoops.org
HARPOCRATE_TOKEN=harp_xxx

# Master key API
RAG_MASTER_KEY=mk_xxx

# URL de l'IHM (pour les redirects OIDC callback)
RAG_PUBLIC_URL=https://rag.yoops.org
```

Le `client_secret` OIDC n'apparaît pas dans le `.env` — il est résolu dynamiquement via Harpocrate au démarrage du service.

---

## Paramétrage OIDC via API (curl)

La config OIDC peut être initialisée ou mise à jour via l'API d'administration :

```bash
# Initialiser la config OIDC
curl -X POST https://rag.yoops.org/admin/oidc \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "issuer": "https://keycloak.yoops.org/realms/homelab",
    "client_id": "rag-service",
    "client_secret_ref": "keycloak_rag_client_secret"
  }'

# Vérifier la config OIDC active
curl https://rag.yoops.org/admin/oidc \
  -H "Authorization: Bearer $RAG_MASTER_KEY"
```

---

## Endpoints protégés par couche

| Endpoint | Protection |
|---|---|
| `GET /ui/*` | OIDC — rôle `rag-viewer` minimum |
| `POST /workspaces` | Bearer master key |
| `GET /workspaces` | Bearer master key |
| `PATCH /workspaces/{name}` | Bearer master key |
| `DELETE /workspaces/{name}` | Bearer master key |
| `GET /workspaces/{name}/apikey` | Bearer master key |
| `POST /workspaces/{name}/sources` | Bearer master key |
| `POST /workspaces/{name}/reindex` | Bearer master key |
| `GET /workspaces/{name}/jobs` | Bearer master key ou OIDC `rag-viewer` |
| `POST /workspaces/{name}/index` | Bearer workspace api_key |
| `POST /mcp` | Bearer workspace api_key |
| `POST /admin/oidc` | Bearer master key |

---

## Keycloak — configuration requise

Dans le realm `homelab`, créer un client `rag-service` :

```
Client ID       : rag-service
Protocol        : openid-connect
Access Type     : confidential
Valid Redirect  : https://rag.yoops.org/auth/callback
Root URL        : https://rag.yoops.org
Roles           : rag-admin, rag-viewer
```

Le `client_secret` généré par Keycloak est stocké dans Harpocrate sous la clé logique `keycloak_rag_client_secret`.
