# 03 — Coffres Harpocrate

Harpocrate est le gestionnaire de secrets utilisé par ag-flow.rag. Le service ne stocke **jamais** de clé API, token ou mot de passe en clair en base de données — tout passe par Harpocrate.

---

## Principe de fonctionnement

Quand vous créez un workspace avec un provider OpenAI, vous ne donnez pas directement la clé API OpenAI au service RAG. Vous donnez une **clé logique** (ex : `openai_embedding_key`) qui fait référence à un secret stocké dans Harpocrate.

```
Workspace "mon-projet"
  api_key_ref = "openai_embedding_key"        ← stocké en DB (jamais le vrai token)
                        │
                        ▼
              SecretResolver.resolve("openai_embedding_key")
                        │
                        ▼
              Harpocrate API → "sk-proj-xxxx..."  ← valeur réelle
                        │
                        ▼
              Utilisée pour l'embedding → immédiatement discardée
```

Le service ne persist jamais la valeur réelle. Elle transite uniquement en mémoire le temps d'un appel API.

---

## Gestion des coffres via l'interface

### Accéder aux coffres

Menu de gauche → **Paramètres** → **Coffres Harpocrate**

### Créer un coffre

1. Cliquez sur **+ Nouveau coffre**
2. Remplissez les champs :

| Champ | Obligatoire | Description |
|---|---|---|
| **Nom** | Oui | Identifiant interne unique (ex : `coffre-principal`, `coffre-backup`) |
| **URL de base** | Oui | URL de l'instance Harpocrate (ex : `https://harpocrate.votre-domaine.fr`) |
| **ID de clé API** | Oui | Identifiant de la clé API Harpocrate (ex : `k-001`) |
| **Clé API** | Oui | Token d'accès Harpocrate — chiffré en base, jamais affiché après |

3. Cliquez **Tester la connexion** pour vérifier
4. Cliquez **Créer le coffre**

> **Note :** `HARPOCRATE_DEK` doit être défini dans votre `.env` avant la création du premier coffre. Cette passphrase chiffre les clés API en base de données.

### Désigner le coffre par défaut

Le coffre par défaut est automatiquement utilisé lors de :
- Création des workspaces (stockage des clés API providers)
- Ajout de sources git (stockage des tokens d'authentification)
- Configuration des webhooks (stockage des headers secrets)

Menu `⋮` → **Désigner comme coffre par défaut**

Un seul coffre peut être le coffre par défaut à la fois.

### Remplacer la clé API d'un coffre

Si votre clé API Harpocrate expire ou est révoquée :

1. Cliquez sur le coffre dans la liste
2. Onglet **Détail**
3. Cliquez **Remplacer la clé**
4. Entrez le nouvel ID de clé et le nouveau token
5. Cliquez **Remplacer**

Le service utilise immédiatement la nouvelle clé sans redémarrage.

### Voir les secrets d'un coffre

L'onglet **Secrets** dans le détail d'un coffre liste les secrets accessibles via la clé API configurée. Cela permet de vérifier que les clés logiques que vous utilisez existent bien dans Harpocrate.

> Le contenu des secrets n'est jamais affiché — seulement les noms/chemins.

---

## Gestion des coffres via l'API

### Lister les coffres

```bash
curl -X GET https://rag.votre-domaine.fr/api/admin/harpocrate-vaults \
  -H "Authorization: Bearer $RAG_MASTER_KEY"
```

Réponse :
```json
[
  {
    "id": "uuid...",
    "name": "coffre-principal",
    "base_url": "https://harpocrate.votre-domaine.fr",
    "api_key_id": "k-001",
    "is_default": true,
    "created_at": "2026-05-31T10:00:00Z"
  }
]
```

### Créer un coffre

```bash
curl -X POST https://rag.votre-domaine.fr/api/admin/harpocrate-vaults \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "coffre-principal",
    "base_url": "https://harpocrate.votre-domaine.fr",
    "api_key_id": "k-001",
    "api_key": "hrpv_1_votre_token_ici"
  }'
```

### Tester la connexion

```bash
curl -X POST https://rag.votre-domaine.fr/api/admin/harpocrate-vaults/{id}/test-connection \
  -H "Authorization: Bearer $RAG_MASTER_KEY"
```

Réponse en cas de succès :
```json
{
  "ok": true,
  "account": "votre-compte",
  "permissions": ["read", "write"]
}
```

### Modifier un coffre

```bash
curl -X PUT https://rag.votre-domaine.fr/api/admin/harpocrate-vaults/{id} \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "api_key_id": "k-002",
    "api_key": "nouveau_token"
  }'
```

### Désigner comme coffre par défaut

```bash
curl -X POST https://rag.votre-domaine.fr/api/admin/harpocrate-vaults/{id}/set-default \
  -H "Authorization: Bearer $RAG_MASTER_KEY"
```

---

## Format des références de secrets

Les références à des secrets dans Harpocrate suivent ce format :

```
${vault://nom-du-coffre:/chemin/vers/le/secret}
```

Exemples :
```
${vault://coffre-principal:/openai/embedding-key}
${vault://coffre-principal:/workspaces/mon-projet/webhook-secret}
${vault://coffre-backup:/github/token-lecture}
```

Dans certains contextes (sources git, webhooks), vous pouvez aussi utiliser une clé logique simple :
```
openai_embedding_key
github_personal_token
keycloak_rag_client_secret
```

La clé logique est résolue automatiquement par rapport au coffre par défaut.

---

## Bonnes pratiques

### Organisation des secrets dans Harpocrate

Adoptez une convention de nommage cohérente :

```
/rag/
├── providers/
│   ├── openai-embedding          ← Clé OpenAI pour l'embedding
│   ├── voyage-embedding          ← Clé Voyage AI
│   ├── anthropic-claude          ← Clé Anthropic pour le playground
│   └── azure-openai              ← Clé Azure OpenAI
│
├── git/
│   ├── github-readonly           ← Token GitHub lecture seule
│   ├── gitlab-deploy             ← Token GitLab deploy key
│   └── azure-devops-pat          ← Personal Access Token Azure
│
├── workspaces/
│   ├── mon-projet/
│   │   └── webhook-notify        ← Secret webhook sortant
│   └── autre-projet/
│       └── webhook-notify
│
└── auth/
    └── keycloak-rag-secret       ← Secret client OIDC Keycloak
```

### Rotation des secrets

Quand vous changez une clé API dans Harpocrate :
1. Le cache interne (valide quelques minutes) expire naturellement
2. Aucun redémarrage requis
3. Toutes les sources et workspaces utilisent automatiquement la nouvelle valeur

### Surveillance

Vérifiez régulièrement la connexion aux coffres :

```bash
# Tester tous les coffres
for vault_id in $(curl -s -H "Authorization: Bearer $RAG_MASTER_KEY" \
  https://rag.votre-domaine.fr/api/admin/harpocrate-vaults | jq -r '.[].id'); do
  echo -n "Test coffre $vault_id: "
  curl -s -X POST \
    -H "Authorization: Bearer $RAG_MASTER_KEY" \
    https://rag.votre-domaine.fr/api/admin/harpocrate-vaults/$vault_id/test-connection \
    | jq -r '.ok'
done
```

---

## Prochaine étape

→ [04 — Workspaces](04-workspaces.md)
