# 16 — Gestion des credentials dans les coffres

Les coffres Harpocrate centralisent trois types de credentials nécessaires au fonctionnement du service RAG : les **clés API providers** (OpenAI, Voyage, etc.), les **tokens git** (GitHub, GitLab, etc.) et les **clés SSH**.

---

## Vue d'ensemble

| Type | Usage | Onglet dans le coffre |
|---|---|---|
| **Clés API providers** | Embedding (OpenAI, Voyage, Cohere) et LLM playground | Apikeys |
| **Credentials git** | Authentification HTTPS sur les dépôts privés | Apikeys → Git |
| **Clés SSH** | Authentification SSH sur les dépôts privés | SSH Keys |

Tous ces credentials sont stockés **chiffrés dans Harpocrate**, jamais en clair dans la base de données RAG. Seule une référence (`harpo_path`) est stockée en DB.

---

## Clés API providers

### Rôle

Les clés API providers sont utilisées pour :
- **Embedding** lors de l'indexation (OpenAI, Voyage, Azure OpenAI, Ollama)
- **LLM** dans le Playground (Anthropic Claude, OpenAI GPT, Azure, Ollama)
- **Reranking** (Cohere, Voyage)

### Accéder à la gestion

1. Menu gauche → **Paramètres** → **Coffres Harpocrate**
2. Cliquez sur votre coffre
3. Onglet **Apikeys**

### Ajouter une clé API provider

1. Cliquez **+ Ajouter une clé API**
2. Remplissez le formulaire :

| Champ | Description | Exemple |
|---|---|---|
| **Identifiant** | Nom unique de la clé dans ce coffre | `openai-embedding-prod` |
| **Label** | Description lisible | `OpenAI — clé embedding production` |
| **Provider** | Fournisseur de l'API | `openai`, `voyage`, `anthropic`, `cohere`, `azure-openai` |
| **Valeur** | La clé API réelle (jamais stockée en clair) | `sk-proj-xxxxx` |
| **Expiration** | Date d'expiration optionnelle | `2027-01-01` ou "Non expirable" |

3. Cliquez **Ajouter**

La clé est immédiatement stockée dans Harpocrate et référençable dans vos workspaces.

### Expiration des clés

Si une date d'expiration est définie, l'interface affiche un **badge d'alerte** quand la clé approche de son expiration. La clé reste fonctionnelle jusqu'à la date indiquée.

Pour renouveler une clé expirée :
1. Cliquez sur la clé dans la liste
2. **Remplacer la valeur**
3. Saisissez la nouvelle valeur + nouvelle date d'expiration
4. Confirmez

### Utiliser une clé dans un workspace

Lors de la création ou modification d'un workspace :
- **Clé API provider** → sélectionnez dans la liste des clés configurées
- La liste affiche les clés par provider, avec leur label et leur statut

### Via l'API

```bash
# Lister les clés d'un coffre
curl -H "Authorization: Bearer $RAG_MASTER_KEY" \
  "https://rag.votre-domaine.fr/api/admin/harpocrate-vaults/{vault_id}/provider-keys"

# Créer une clé API
curl -X POST "https://rag.votre-domaine.fr/api/admin/harpocrate-vaults/{vault_id}/provider-keys" \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "key_id": "openai-embedding-prod",
    "label": "OpenAI embedding production",
    "provider": "openai",
    "value": "sk-proj-xxxxx"
  }'
```

---

## Credentials git (tokens HTTPS)

### Rôle

Les tokens git permettent d'authentifier le service RAG sur les dépôts privés via HTTPS :
- GitHub Personal Access Token
- GitLab Project Access Token / Personal Access Token
- Gitea Personal Access Token
- Bitbucket App Password
- Azure DevOps Personal Access Token

### Ajouter un token git

1. Onglet **Apikeys** du coffre → **Credentials git**
2. Cliquez **+ Ajouter un credential git**
3. Remplissez :

| Champ | Description | Exemple |
|---|---|---|
| **Identifiant** | Nom unique | `github-readonly-org` |
| **Label** | Description | `GitHub — lecture repos mon-org` |
| **Hôte** | Provider git | `github`, `gitlab`, `gitea`, `bitbucket`, `azure-devops` |
| **URL de scope** | Limiter à un dépôt ou org (optionnel) | `https://github.com/mon-org` |
| **Valeur** | Le token réel | `ghp_xxxxx` |
| **Expiration** | Date d'expiration optionnelle | `2027-06-01` |

4. Cliquez **Ajouter**

### Permissions minimales recommandées par provider

**GitHub :**
- Fine-grained token : `Contents` → **Read-only**
- Classic token : scope `repo` (ou `public_repo` pour les repos publics)

**GitLab :**
- Scope : `read_repository`

**Bitbucket :**
- Permission : `Repositories` → **Read**

**Azure DevOps :**
- Scope : `Code` → **Read**

**Gitea :**
- Permission : `repository` → **Read**

### Utiliser un credential dans une source git

Lors de l'ajout d'une source git dans un workspace :
- **Type d'auth** → `Token`
- **Credential** → sélectionnez dans la liste (filtrée par hôte)

### Via l'API

```bash
# Créer un credential git
curl -X POST "https://rag.votre-domaine.fr/api/admin/git-credentials" \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "vault_id": "uuid-du-coffre",
    "key_id": "github-readonly-org",
    "label": "GitHub — lecture repos mon-org",
    "host": "github",
    "scope_url": "https://github.com/mon-org",
    "value": "ghp_xxxxx"
  }'
```

---

## Clés SSH

### Rôle

Les clés SSH permettent l'authentification SSH pour les dépôts git privés. Utiles quand :
- Votre organisation interdit les tokens HTTPS
- Vous préférez une authentification par certificat
- Les dépôts self-hosted (Gitea, GitLab on-premise) utilisent SSH

### Ajouter une clé SSH

1. Onglet **SSH Keys** du coffre
2. Cliquez **+ Ajouter une clé SSH**
3. Remplissez :

| Champ | Description |
|---|---|
| **Identifiant** | Nom unique dans le coffre |
| **Nom** | Label lisible |
| **Type** | `ed25519` (recommandé), `rsa-4096`, ou `ecdsa-256` |
| **Clé privée** | Contenu complet de la clé privée (`-----BEGIN ...`) |
| **Passphrase protégée** | Si la clé privée est chiffrée par une passphrase |

4. Cliquez **Ajouter**

### Générer une paire de clés dédiée

Générez une paire de clés SSH spécifique au service RAG (ne réutilisez pas votre clé personnelle) :

```bash
# Générer une clé Ed25519 (recommandée)
ssh-keygen -t ed25519 -C "rag-service@votre-domaine.fr" -f ~/.ssh/rag_service_ed25519
# Ne pas mettre de passphrase pour un usage non-interactif

# Afficher la clé publique à copier dans GitHub/GitLab
cat ~/.ssh/rag_service_ed25519.pub

# Afficher la clé privée à coller dans le coffre
cat ~/.ssh/rag_service_ed25519
```

### Déployer la clé publique

**GitHub (Deploy Key) :**
1. Dépôt → Settings → Deploy keys → Add deploy key
2. Coller la clé **publique** (`*.pub`)
3. Cocher **Allow write access** uniquement si nécessaire (lecture seule recommandée)

**GitLab (Deploy Key) :**
1. Dépôt → Settings → Repository → Deploy keys → Expand → Add new deploy key
2. Coller la clé publique

**Gitea :**
1. Site Administration → Deploy Keys → Add Key (pour toute l'instance)
2. Ou dépôt → Settings → Deploy Keys → Add Key

**Bitbucket :**
1. Repository Settings → Access keys → Add key
2. Coller la clé publique

**Azure DevOps :**
1. User Settings → SSH Public Keys → Add
2. Coller la clé publique

### Utiliser une clé SSH dans une source git

Lors de l'ajout d'une source git :
- **Type d'auth** → `SSH`
- **Clé SSH** → sélectionnez dans la liste
- **URL** → format SSH : `git@github.com:mon-org/mon-repo.git`

---

## Rotation et renouvellement

### Clé API expirée

1. Coffre → Apikeys → clé concernée → **Modifier**
2. Saisir la nouvelle valeur + nouvelle date d'expiration
3. Sauvegarder

Le changement est immédiatement pris en compte (le cache interne expire naturellement en quelques minutes).

### Token git compromis

1. **Révoquer immédiatement** le token sur GitHub/GitLab/etc.
2. Générer un nouveau token
3. Dans le coffre : clé concernée → **Modifier** → saisir la nouvelle valeur
4. Aucun redémarrage requis

### Clé SSH compromise

1. **Supprimer la clé publique** des Deploy Keys sur GitHub/GitLab
2. Générer une nouvelle paire de clés
3. Déployer la nouvelle clé publique
4. Dans le coffre : supprimer l'ancienne clé SSH → ajouter la nouvelle
5. Mettre à jour les sources git qui référençaient l'ancienne clé

---

## Audit et surveillance

### Credentials expirés

L'interface affiche un **badge rouge** sur les credentials expirés. Vérifiez régulièrement :

1. Coffre → Apikeys — badges d'expiration visibles sur chaque ligne
2. Testez la connexion du coffre pour détecter les tokens révoqués

### Via l'API

```bash
# Lister les credentials avec leurs dates d'expiration
curl -H "Authorization: Bearer $RAG_MASTER_KEY" \
  "https://rag.votre-domaine.fr/api/admin/git-credentials" \
  | jq '.[] | {label, host, expires_at}'

curl -H "Authorization: Bearer $RAG_MASTER_KEY" \
  "https://rag.votre-domaine.fr/api/admin/harpocrate-vaults/{vault_id}/provider-keys" \
  | jq '.[] | {label, provider, expires_at}'
```

---

## Résumé des références utilisées dans les sources

Quand vous configurez une source git dans un workspace, la référence au credential est stockée dans le champ `config.auth_ref` (pour les tokens) ou `config.ssh_key_ref` (pour les clés SSH) du JSONB de la source. Ces références pointent vers le `harpo_path` du credential dans Harpocrate.

```json
// workspace_sources.config (JSONB)
{
  "url": "https://github.com/mon-org/mon-repo",
  "branch": "main",
  "git_provider": "github",
  "auth_type": "token",
  "auth_ref": "${vault://coffre-principal:/git/github-readonly-org}"
}
```

Jamais de token en clair dans ce champ.
