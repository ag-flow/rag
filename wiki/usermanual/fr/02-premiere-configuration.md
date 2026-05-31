# 02 — Première configuration

Ce guide vous accompagne du premier démarrage jusqu'à un service pleinement opérationnel.

---

## Étape 1 : Premier accès — compte bootstrap local

Au premier démarrage, si `RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH` est vide dans votre `.env`, le service génère automatiquement un mot de passe administrateur et l'affiche dans les logs :

```bash
# Voir le mot de passe généré
docker compose logs rag-service | grep "bootstrap"

# Exemple de sortie
[INFO] Bootstrap admin created: username=admin password=Xk9pL2mQ7rTw
```

> **Important :** Notez ce mot de passe immédiatement. Il n'est affiché qu'une seule fois.

Accédez à l'interface :

```
http://votre-serveur:8000/ui
```

Vous verrez la page de connexion. Utilisez :
- **Identifiant :** `admin` (ou la valeur de `RAG_BOOTSTRAP_ADMIN_USERNAME`)
- **Mot de passe :** celui affiché dans les logs

---

## Étape 2 : Générer les secrets de configuration

Avant de continuer, générez des valeurs sécurisées pour votre `.env` si ce n'est pas encore fait :

```bash
# RAG_MASTER_KEY
echo "mk_$(openssl rand -hex 24)"

# HARPOCRATE_DEK (doit faire au moins 32 caractères)
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

# RAG_SESSION_SECRET
openssl rand -hex 32

# RAG_WEBHOOK_SECRET
openssl rand -hex 32
```

Mettez à jour votre `.env` avec ces valeurs, puis redémarrez le service.

---

## Étape 3 : Configurer le coffre Harpocrate

Harpocrate est un gestionnaire de secrets. Le service RAG l'utilise pour stocker toutes les clés API (OpenAI, GitHub tokens, etc.) sans jamais les écrire en clair en base de données.

> **Prérequis :** Vous devez avoir une instance Harpocrate accessible. Si vous n'en avez pas, vous pouvez utiliser une instance auto-hébergée ou le service Harpocrate cloud.

> **Requis :** `HARPOCRATE_DEK` doit être défini dans votre `.env` avant de créer un coffre.

### 3.1 Accéder à la gestion des coffres

Depuis l'interface admin :
1. Cliquez sur **Paramètres** dans le menu de gauche
2. Cliquez sur **Coffres Harpocrate**
3. Cliquez sur **+ Nouveau coffre**

### 3.2 Remplir le formulaire

| Champ | Description | Exemple |
|---|---|---|
| **Nom** | Identifiant interne du coffre (alphanum, tirets) | `harpocrate-principal` |
| **URL de base** | URL de l'instance Harpocrate | `https://harpocrate.votre-domaine.fr` |
| **ID de clé API** | Identifiant de votre clé API Harpocrate | `k-001` |
| **Clé API** | Token d'accès Harpocrate (jamais stocké en clair) | `hrpv_1_xxxxx` |

### 3.3 Tester la connexion

Cliquez sur **Tester la connexion** avant de sauvegarder. Le service vérifie que :
- L'URL est joignable
- La clé API est valide
- Les permissions sont suffisantes

En cas de succès, un message vert s'affiche avec les informations du compte Harpocrate.

### 3.4 Désigner le coffre par défaut

Si vous avez plusieurs coffres, désignez-en un comme coffre par défaut. Ce coffre sera automatiquement utilisé lors de la création des workspaces et des sources git.

Cliquez sur le menu `⋮` à côté du coffre, puis **Désigner comme coffre par défaut**.

---

## Étape 4 : Configurer OIDC (Keycloak)

L'authentification SSO via OIDC est optionnelle mais recommandée pour un usage multi-utilisateurs. Sans OIDC, seul le compte bootstrap local fonctionne.

> **Prérequis :**
> - Une instance Keycloak accessible
> - Un realm configuré (ex : `homelab`, `production`)
> - Le client `rag-service` créé dans Keycloak
> - La clé secrète du client stockée dans votre coffre Harpocrate

### 4.1 Créer le client Keycloak

Dans l'interface Keycloak :

1. **Créer un client** :
   - Client ID : `rag-service`
   - Client Protocol : `openid-connect`
   - Access Type : `confidential`

2. **Configurer les URLs** :
   - Valid Redirect URIs : `https://rag.votre-domaine.fr/auth/callback`
   - Web Origins : `https://rag.votre-domaine.fr`

3. **Créer les rôles** (dans l'onglet Roles du client) :
   - `rag-admin` — accès complet (lecture + écriture)
   - `rag-viewer` — lecture seule

4. **Assigner les rôles** à vos utilisateurs dans Keycloak

5. **Copier le client_secret** depuis l'onglet Credentials

### 4.2 Stocker le secret dans Harpocrate

Avant de configurer OIDC dans RAG, stockez le `client_secret` dans votre coffre Harpocrate :

```bash
# Via l'API Harpocrate (exemple)
curl -X POST https://harpocrate.votre-domaine.fr/secrets \
  -H "Authorization: Bearer $HARPOCRATE_TOKEN" \
  -d '{"key": "keycloak_rag_client_secret", "value": "votre-client-secret"}'
```

Notez le nom de la clé logique que vous avez choisi (ici : `keycloak_rag_client_secret`).

### 4.3 Configurer OIDC dans RAG

**Via l'interface** (recommandé) :
1. Allez dans **Paramètres > OIDC**
2. Remplissez le formulaire :

| Champ | Description | Exemple |
|---|---|---|
| **Issuer** | URL du realm Keycloak | `https://keycloak.votre-domaine.fr/realms/homelab` |
| **Client ID** | Identifiant du client Keycloak | `rag-service` |
| **Référence secret client** | Clé logique Harpocrate (PAS le secret lui-même) | `keycloak_rag_client_secret` |

3. Cliquez **Configurer OIDC**

**Via l'API** (automatisation) :
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

### 4.4 Tester l'authentification OIDC

1. Ouvrez une fenêtre de navigation privée
2. Accédez à `https://rag.votre-domaine.fr/ui`
3. Vous devriez être redirigé vers Keycloak
4. Connectez-vous avec un compte ayant le rôle `rag-admin`
5. Vous devriez être redirigé vers le tableau de bord RAG

---

## Étape 5 : Créer le premier workspace

Un **workspace** est un espace d'indexation dédié à un projet ou un corpus. Chaque workspace a :
- Sa propre base de données pgvector
- Son propre modèle d'embedding (immutable)
- Ses propres sources git, clés API et webhooks

### 5.1 Via l'interface

1. Cliquez sur **+ New** dans la sidebar des Workspaces
2. Remplissez le formulaire :

**Informations de base :**
- **Nom** : identifiant unique, minuscules, tirets autorisés (ex : `mon-projet`, `harpocrate-docs`)

**Modèle d'indexation :** (ce choix est **définitif**)

| Champ | Description |
|---|---|
| **Provider** | Fournisseur d'embedding (voir tableau ci-dessous) |
| **Modèle** | Modèle d'embedding selon le provider |
| **URL de base** | Uniquement pour Ollama (ex : `http://192.168.1.100:11434`) |
| **Clé API (provider)** | Sélectionner dans la liste des clés configurées |

**Reranking (optionnel) :**
- Améliore la qualité des résultats en post-processing
- Cohere ou Voyage recommandés

**Providers d'embedding disponibles :**

| Provider | Modèles | Dimension | Usage recommandé |
|---|---|---|---|
| `openai` | `text-embedding-3-small` | 1536 | Général, bon rapport qualité/coût |
| `openai` | `text-embedding-3-large` | 3072 | Précision maximale |
| `voyage` | `voyage-3` | 1024 | Meilleure qualité RAG |
| `voyage` | `voyage-code-3` | 1024 | Corpus de code source |
| `azure-openai` | `text-embedding-3-small` | 1536 | Données internes Azure |
| `ollama` | `qwen2.5-coder:14b` | 4096 | Données sensibles, zéro coût |
| `ollama` | `nomic-embed-text` | 768 | Texte général, léger |

> **Attention :** Le provider et le modèle d'indexation ne peuvent pas être changés après création sans réindexation complète.

### 5.2 Via l'API

```bash
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "mon-projet",
    "indexer": {
      "provider": "openai",
      "model": "text-embedding-3-small",
      "api_key_ref": "openai_embedding_key"
    }
  }'
```

> Réponse : `201 Created` avec l'ID du workspace et une première clé API.

---

## Étape 6 : Ajouter une source git

Voir [05 — Sources git](05-sources-git.md) pour le guide complet.

---

## Checklist de démarrage

- [ ] Service démarré et accessible sur `:8000`
- [ ] Connexion avec le compte bootstrap local
- [ ] Coffre Harpocrate créé et testé
- [ ] OIDC configuré (optionnel mais recommandé)
- [ ] Premier workspace créé
- [ ] Première source git ajoutée
- [ ] Clé API workspace récupérée (pour Claude Code)

---

## Prochaine étape

→ [03 — Coffres Harpocrate](03-harpocrate.md)
