# 05 — Sources git

Les sources git sont des dépôts surveillés automatiquement par le service RAG. Quand du nouveau contenu est détecté (commit, push), le service indexe les fichiers modifiés.

---

## Modes de synchronisation

Le service supporte deux modes de déclenchement, **mutuellement exclusifs** par source :

### Mode Polling (Schedule)

Le service scrute périodiquement le dépôt git pour détecter les changements.

- **Intervalle par défaut :** 5 minutes (configurable via `SYNC_DEFAULT_INTERVAL_SECONDS`)
- **Override par source :** champ `sync_interval_seconds` dans la configuration (minimum 60s)
- **Indicateur :** badge gris **Schedule** sur la ligne de la source

### Mode Webhook (Push réactif)

Le dépôt git notifie le service RAG lors de chaque push via un webhook entrant.

- **Réaction immédiate** : indexation déclenchée en quelques secondes
- **Providers supportés :** GitHub, GitLab, Gitea, Bitbucket, Azure DevOps
- **Indicateur :** badge vert **Webhook** sur la ligne de la source

> Quand le mode webhook est activé, le polling est automatiquement désactivé pour cette source. Si vous désactivez le webhook, le polling reprend immédiatement.

---

## Ajouter une source git

### Via l'interface

1. Onglet **Git sources** du workspace
2. Cliquez **+ Ajouter une source**
3. Remplissez le formulaire :

**Nom de la source**
- Identifiant unique dans le workspace
- Exemples : `docs-principal`, `code-src`, `wiki`

**Provider git**
- GitHub, GitLab, Gitea, Bitbucket, Azure DevOps, ou générique

**URL du dépôt**
- Format HTTPS : `https://github.com/mon-org/mon-repo`
- Format SSH : `git@github.com:mon-org/mon-repo.git`

**Branche**
- La liste des branches disponibles est chargée automatiquement après saisie de l'URL
- Sélectionnez dans la liste déroulante ou saisissez manuellement
- Laissez vide pour détecter automatiquement la branche par défaut

**Type d'authentification**

| Type | Quand l'utiliser |
|---|---|
| **Aucune** | Dépôt public |
| **Token** | HTTPS avec token GitHub/GitLab/etc. |
| **SSH** | Accès via clé SSH |

**Credential** (si Token ou SSH)
- Sélectionnez parmi les credentials configurés dans votre coffre Harpocrate
- Si absent, configurez d'abord le credential via [03 — Harpocrate](03-harpocrate.md)

**Filtres** (optionnel)
- **Include patterns** : `**/*.md`, `docs/**`, `src/**/*.ts` — seuls ces fichiers sont indexés
- **Exclude patterns** : `node_modules/**`, `*.lock`, `.git/**` — ces fichiers sont ignorés

### Via l'API

```bash
# Dépôt public sans authentification
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/sources \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "docs-public",
    "type": "git",
    "config": {
      "url": "https://github.com/mon-org/mon-repo",
      "branch": "main",
      "include": ["**/*.md", "**/*.rst"],
      "exclude": ["node_modules/**", ".git/**"]
    }
  }'
```

```bash
# Dépôt privé GitHub avec token
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/sources \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "code-prive",
    "type": "git",
    "git_provider": "github",
    "auth_type": "token",
    "auth_ref": "github_personal_token",
    "config": {
      "url": "https://github.com/mon-org/repo-prive",
      "branch": "develop",
      "include": ["src/**/*.ts", "src/**/*.py", "docs/**/*.md"]
    }
  }'
```

```bash
# Dépôt via SSH
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/sources \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "repo-ssh",
    "type": "git",
    "auth_type": "ssh",
    "ssh_key_ref": "ma_cle_ssh_ed25519",
    "config": {
      "url": "git@github.com:mon-org/repo.git",
      "branch": "main"
    }
  }'
```

---

## Configurer l'authentification

### Tokens d'accès (HTTPS)

Pour les dépôts privés GitHub, GitLab, etc., créez d'abord un **token d'accès personnel** avec les permissions minimales :

**GitHub** :
- Allez dans **Settings > Developer settings > Personal access tokens**
- Créez un token avec la portée `repo` (lecture seule suffit : `repo:status`, `public_repo` ou `repo` pour les repos privés)
- Ou utilisez un **Fine-grained token** avec `Contents: Read-only`

**GitLab** :
- Allez dans **Préférences > Access Tokens**
- Portée minimale : `read_repository`

**Azure DevOps** :
- Allez dans **User settings > Personal Access Tokens**
- Portée : `Code > Read`

Stockez ce token dans Harpocrate, puis référencez la clé logique dans votre source.

### Clés SSH

Si vous préférez l'authentification SSH :

1. **Générez une paire de clés** dédiée au service RAG (ne réutilisez pas votre clé personnelle) :
   ```bash
   ssh-keygen -t ed25519 -C "rag-service@votre-domaine.fr" -f ~/.ssh/rag_service
   ```

2. **Ajoutez la clé publique** dans votre dépôt :
   - GitHub : Settings > Deploy keys > Add deploy key
   - GitLab : Settings > Repository > Deploy keys
   - Bitbucket : Repository settings > Access keys

3. **Stockez la clé privée** dans Harpocrate

4. **Référencez-la** lors de l'ajout de la source avec `auth_type: "ssh"` et `ssh_key_ref`

---

## Activer le mode webhook (push réactif)

### Étape 1 : Activer le webhook dans RAG

1. Onglet **Git sources** du workspace
2. Sur la ligne de la source, cliquez le menu `⋮`
3. Cliquez **Activer le webhook**
4. Une dialog s'ouvre avec :
   - **L'URL du webhook** à configurer dans votre provider git
   - **Le secret** généré (copiez-le maintenant — il ne sera plus affiché)

> **Important :** Le secret est généré une seule fois et stocké chiffré dans Harpocrate. Si vous le perdez, utilisez **Rotation du secret** pour en générer un nouveau.

### Étape 2 : Configurer le webhook dans votre provider git

**GitHub :**
1. Settings > Webhooks > Add webhook
2. **Payload URL** : URL copiée depuis RAG
3. **Content type** : `application/json`
4. **Secret** : le secret copié depuis RAG
5. **Événements** : sélectionnez **Just the push event**
6. Cliquez **Add webhook**

**GitLab :**
1. Settings > Webhooks
2. **URL** : URL copiée depuis RAG
3. **Secret token** : le secret copié depuis RAG
4. **Trigger** : cochez **Push events**
5. Cliquez **Add webhook**

**Gitea :**
1. Settings > Webhooks > Add Webhook > Gitea
2. **Target URL** : URL copiée depuis RAG
3. **Secret** : le secret copié depuis RAG
4. **Trigger On** : Push Events
5. Cliquez **Add Webhook**

**Bitbucket :**
1. Repository Settings > Webhooks > Add webhook
2. **URL** : URL copiée depuis RAG
3. **Secret key** : le secret copié depuis RAG
4. **Triggers** : Repository push
5. Cliquez **Save**

**Azure DevOps :**
1. Project Settings > Service Hooks > Create subscription
2. **Service** : Web Hooks
3. **Trigger** : Code pushed
4. **URL** : URL copiée depuis RAG
5. **Basic authentication password** : le secret copié depuis RAG

### URL du webhook entrant

L'URL a le format :
```
https://rag.votre-domaine.fr/api/webhooks/git/{workspace_name}/{source_name}
```

### Filtrage par branche

Le webhook n'indexe que les pushs sur la **branche configurée** dans la source (ex : `main`). Les pushs sur d'autres branches sont ignorés silencieusement (HTTP 200 retourné, aucun job créé).

### Rotation du secret webhook

En cas de compromission du secret :
1. Menu `⋮` sur la source > **Rotation du secret**
2. **Copiez le nouveau secret**
3. Mettez à jour le secret dans les paramètres webhook de votre provider git

### Désactiver le webhook

Menu `⋮` sur la source > **Désactiver le webhook**

La source repasse automatiquement en mode polling.

---

## Tester la connexion

Avant de sauvegarder, testez que le service peut accéder au dépôt :

**Via l'interface :**
Cliquez **Tester la connexion** dans le formulaire d'ajout de source.

**Via l'API :**
```bash
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/sources/{source_id}/test \
  -H "Authorization: Bearer $RAG_MASTER_KEY"

# Réponse en cas de succès
{"success": true, "message": null}

# Réponse en cas d'échec
{"success": false, "message": "Authentication failed: Repository not found or no access"}
```

---

## Supprimer une source

> La suppression arrête la synchronisation mais ne supprime pas les documents déjà indexés.

**Via l'interface :** Menu `⋮` > **Supprimer la source**

**Via l'API :**
```bash
curl -X DELETE https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/sources/{source_id} \
  -H "Authorization: Bearer $RAG_MASTER_KEY"
```

---

## Patterns de filtrage (glob)

Le service utilise la syntaxe glob standard pour les filtres `include` et `exclude` :

| Pattern | Correspond à |
|---|---|
| `**/*.md` | Tous les fichiers Markdown à n'importe quelle profondeur |
| `docs/**` | Tout le contenu du répertoire `docs/` |
| `src/**/*.ts` | Fichiers TypeScript dans `src/` |
| `*.json` | Fichiers JSON à la racine uniquement |
| `!test/**` | Exclure le répertoire `test/` (préfixe `!`) |

**Exemples de configurations courantes :**

```json
// Documentation uniquement
{
  "include": ["**/*.md", "**/*.rst", "**/*.txt"],
  "exclude": ["node_modules/**", ".git/**", "CHANGELOG*"]
}

// Code source TypeScript/Python
{
  "include": ["src/**/*.ts", "src/**/*.tsx", "**/*.py"],
  "exclude": ["node_modules/**", "dist/**", "**/*.test.ts", "**/*.spec.py"]
}

// Tout sauf binaires et builds
{
  "include": ["**/*"],
  "exclude": ["node_modules/**", "dist/**", "build/**", "**/*.jpg", "**/*.png", "**/*.pdf"]
}
```

---

## Prochaine étape

→ [06 — Service MCP](06-mcp.md)
