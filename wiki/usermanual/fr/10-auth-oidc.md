# 10 — Authentification OIDC

ag-flow.rag supporte deux systèmes d'authentification complémentaires :

1. **OIDC (Keycloak)** — pour l'interface web et le Playground (utilisateurs humains)
2. **Bearer tokens** — pour l'API REST et le MCP (accès programmatique)

---

## Vue d'ensemble

### Couche 1 : Interface web — OIDC

| Aspect | Détail |
|---|---|
| **Protocole** | OpenID Connect (OIDC) |
| **Provider recommandé** | Keycloak |
| **Périmètre** | Routes `/ui/*` et `/api/workspaces/*/playground/*` |
| **Session** | Cookie `_oidc_session` signé (TTL configurable) |
| **Rôles** | `rag-admin` (lecture/écriture) et `rag-viewer` (lecture seule) |

### Couche 2 : API REST et MCP — Bearer tokens

| Aspect | Détail |
|---|---|
| **Protocole** | HTTP Bearer token |
| **Tokens** | `RAG_MASTER_KEY` (admin) ou clé API workspace |
| **Périmètre** | `/api/admin/*`, `/api/webhooks/git/*`, `/mcp/*` |
| **Pas de session** | Stateless, token vérifié à chaque requête |

---

## Rôles OIDC

### `rag-admin`

Accès complet à l'interface et à toutes les fonctionnalités :
- Créer, modifier, supprimer des workspaces
- Gérer les sources git, webhooks, LLM configs
- Accéder au Playground
- Modifier les paramètres (OIDC, Harpocrate)
- Configurer les triggers et prompts

### `rag-viewer`

Accès en lecture seule :
- Voir les workspaces et leurs configurations
- Consulter les jobs et l'historique
- Accéder au Playground (utilisation uniquement, pas de configuration)

> Les rôles sont définis dans le **client** Keycloak `rag-service` (pas dans les rôles de realm). Chaque utilisateur doit avoir le rôle assigné dans le client.

---

## Configurer Keycloak

### Créer le realm (si inexistant)

Dans l'interface Keycloak :
1. Cliquez sur le sélecteur de realm (haut gauche)
2. **Create realm**
3. Nom : `homelab` (ou selon votre convention)
4. **Create**

### Créer le client

1. Menu **Clients** → **Create client**
2. Remplissez :
   - **Client type** : `OpenID Connect`
   - **Client ID** : `rag-service`
   - **Name** : `ag-flow.rag`
3. Page suivante :
   - **Client authentication** : `On` (client confidentiel)
   - **Authentication flow** : `Standard flow` uniquement
4. Page suivante :
   - **Valid redirect URIs** : `https://rag.votre-domaine.fr/auth/callback`
   - **Valid post logout redirect URIs** : `https://rag.votre-domaine.fr/ui`
   - **Web origins** : `https://rag.votre-domaine.fr`
5. **Save**

### Créer les rôles du client

1. Ouvrez le client `rag-service`
2. Onglet **Roles** → **Create role**
3. Créez `rag-admin`
4. Créez `rag-viewer`

### Assigner les rôles aux utilisateurs

1. Menu **Users** → sélectionnez un utilisateur
2. Onglet **Role mapping**
3. **Assign role** → filtrez par **Filter by clients** → `rag-service`
4. Sélectionnez `rag-admin` ou `rag-viewer`

### Récupérer le client secret

1. Client `rag-service` → onglet **Credentials**
2. Copiez le **Client secret**

---

## Stocker le secret dans Harpocrate

Avant de configurer l'OIDC dans RAG, stockez le `client_secret` dans votre coffre Harpocrate sous une clé logique.

Exemple via l'API Harpocrate :
```bash
# Adapter selon l'API de votre instance Harpocrate
curl -X PUT https://harpocrate.votre-domaine.fr/secrets/keycloak_rag_client_secret \
  -H "Authorization: Bearer $HARPOCRATE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"value": "votre-client-secret-keycloak"}'
```

> **Note :** Ne jamais mettre le `client_secret` directement dans la configuration RAG ou dans le `.env`. Il doit passer par Harpocrate.

---

## Configurer OIDC dans RAG

### Via l'interface

1. **Paramètres** → **OIDC**
2. Remplissez le formulaire :

| Champ | Exemple | Description |
|---|---|---|
| **Issuer** | `https://keycloak.votre-domaine.fr/realms/homelab` | URL du realm Keycloak |
| **Client ID** | `rag-service` | ID du client Keycloak |
| **Référence secret client** | `keycloak_rag_client_secret` | Clé logique dans Harpocrate (pas le secret lui-même) |

3. Cliquez **Configurer OIDC**

### Via l'API

```bash
curl -X POST https://rag.votre-domaine.fr/api/admin/oidc \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "issuer": "https://keycloak.votre-domaine.fr/realms/homelab",
    "client_id": "rag-service",
    "client_secret_ref": "keycloak_rag_client_secret"
  }'
```

### Vérifier la configuration

```bash
curl -H "Authorization: Bearer $RAG_MASTER_KEY" \
  https://rag.votre-domaine.fr/api/admin/oidc

# Réponse
{
  "configured": true,
  "issuer": "https://keycloak.votre-domaine.fr/realms/homelab",
  "client_id": "rag-service"
}
```

---

## Flow d'authentification

```
1. Utilisateur → https://rag.votre-domaine.fr/ui

2. Service RAG détecte : pas de session valide
   → Redirect vers Keycloak

3. Keycloak → https://keycloak.votre-domaine.fr/realms/homelab/protocol/openid-connect/auth
   ?client_id=rag-service
   &redirect_uri=https://rag.votre-domaine.fr/auth/callback
   &response_type=code
   &scope=openid profile email

4. Utilisateur s'authentifie sur Keycloak

5. Keycloak → Redirect vers https://rag.votre-domaine.fr/auth/callback?code=xxx

6. Service RAG échange le code contre des tokens
   (utilise client_secret résolu depuis Harpocrate)

7. Service crée une session → Cookie _oidc_session

8. Utilisateur → Interface RAG
```

---

## Durée de session

La durée de session est contrôlée par `RAG_BOOTSTRAP_SESSION_TTL_SECONDS` (défaut : 28800 = 8 heures).

Modifiez dans votre `.env` :
```bash
RAG_BOOTSTRAP_SESSION_TTL_SECONDS=86400  # 24 heures
```

---

## Méthodes d'authentification disponibles

Consultez les méthodes actives sans authentification :

```bash
curl https://rag.votre-domaine.fr/auth/methods

# Réponse si OIDC et bootstrap configurés
{
  "methods": ["oidc", "local"],
  "oidc_issuer": "https://keycloak.votre-domaine.fr/realms/homelab"
}

# Réponse si OIDC uniquement (bootstrap désactivé)
{
  "methods": ["oidc"],
  "oidc_issuer": "https://keycloak.votre-domaine.fr/realms/homelab"
}
```

---

## Désactiver le compte bootstrap local

Une fois OIDC configuré et testé, désactivez le compte local pour la sécurité :

```bash
# Dans .env : supprimer ou vider ces lignes
RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH=
# Le compte local sera désactivé au prochain redémarrage
```

---

## Résolution des problèmes OIDC

### Redirect loop

- Vérifiez que `RAG_PUBLIC_URL` correspond exactement à l'URL configurée dans Keycloak (Valid redirect URIs)
- Vérifiez que `RAG_SESSION_SECRET` fait au moins 32 caractères

### Erreur "client_secret_ref not found"

- Vérifiez que la clé logique existe dans Harpocrate
- Testez la connexion au coffre Harpocrate
- Vérifiez que `HARPOCRATE_DEK` est correctement configuré

### Accès refusé après connexion Keycloak

- Vérifiez que l'utilisateur a bien le rôle `rag-admin` ou `rag-viewer` assigné dans le client `rag-service`
- Les rôles de realm ne suffisent pas — ils doivent être dans le client

### Token invalide ou expiré

- Déconnectez-vous et reconnectez-vous
- Vérifiez la synchronisation de l'heure entre le serveur RAG et Keycloak (NTP)

---

## Prochaine étape

→ [11 — Référence API](11-api-reference.md)
