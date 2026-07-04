# Guide de déploiement — ag-flow.rag

Production sur un hôte Linux avec Docker 24+ et Compose v2+.
Architecture : Caddy (port 80) → backend FastAPI + frontend Nginx, Postgres en interne.
TLS géré par Cloudflare Tunnel en front — aucun certificat à gérer sur l'hôte.

---

## Prérequis

| Logiciel | Version minimale |
|---|---|
| Docker Engine | 24+ |
| Docker Compose (plugin) | v2.20+ |
| Accès réseau | Lecture de `ghcr.io` (images publiques, pas de login requis) |

---

## Étape 1 — Créer le répertoire de déploiement

```bash
mkdir -p /opt/rag && cd /opt/rag
```

---

## Étape 2 — Récupérer les fichiers de configuration

Télécharger les trois fichiers nécessaires depuis le dépôt :

```bash
# Compose prod
curl -Lo docker-compose.prod.yml \
  https://raw.githubusercontent.com/ag-flow/rag/main/docker-compose.prod.yml

# Caddyfile (reverse proxy)
curl -Lo Caddyfile \
  https://raw.githubusercontent.com/ag-flow/rag/main/Caddyfile

# Tarifs providers d'embedding (monté en lecture seule dans le backend)
curl -Lo embedding_providers_pricing.yml \
  https://raw.githubusercontent.com/ag-flow/rag/main/embedding_providers_pricing.yml

# Template de configuration
curl -Lo .env.prod.example \
  https://raw.githubusercontent.com/ag-flow/rag/main/.env.prod.example
```

---

## Étape 3 — Créer et remplir le fichier `.env`

```bash
cp .env.prod.example .env
chmod 600 .env   # lecture réservée à root
```

Ouvrir `.env` et renseigner chaque variable. Le tableau ci-dessous détaille
ce qui est obligatoire, ce qui est optionnel, et comment générer chaque valeur.

### Variables obligatoires

| Variable | Description | Commande de génération |
|---|---|---|
| `POSTGRES_PASSWORD` | Mot de passe Postgres | `openssl rand -hex 24` |
| `DATABASE_URL` | DSN applicatif | Remplacer `CHANGEME` par `POSTGRES_PASSWORD` |
| `RAG_POSTGRES_ADMIN_URL` | DSN admin (base `postgres`) | Remplacer `CHANGEME` par `POSTGRES_PASSWORD` |
| `RAG_MASTER_KEY` | Clé Bearer `/api/admin/*` | `openssl rand -hex 32` |
| `RAG_SESSION_SECRET` | Signature cookies session | `openssl rand -hex 32` |
| `RAG_PUBLIC_URL` | URL externe (`https://rag.example.com`) | URL réelle de votre instance |
| `RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH` | Hash bcrypt du 1er mot de passe admin | Voir ci-dessous |

### Générer le hash du mot de passe admin

```bash
# Avec Python (disponible sur tout système Linux)
python3 -c "
import getpass, bcrypt
pwd = getpass.getpass('Mot de passe admin : ').encode()
print(bcrypt.hashpw(pwd, bcrypt.gensalt(12)).decode())
"
```

Coller la sortie (commence par `$2b$12$…`) dans `RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH`.

> **Note** : si `bcrypt` n'est pas installé : `pip install bcrypt` ou
> `apt-get install -y python3-bcrypt`.

### Variables optionnelles notables

| Variable | Rôle | Défaut |
|---|---|---|
| `HARPOCRATE_DEK` | Chiffrement pgcrypto des api_keys | Vide (obligatoire dès le 1er coffre créé) |
| `RAG_WEBHOOK_SECRET` | Signature HMAC des webhooks | Vide (webhooks sans signature) |
| `IMAGE_TAG` | Tag image GHCR à déployer | `latest` |
| `CADDY_HTTP_PORT` | Port hôte de Caddy | `80` |
| `GIT_SHA` | SHA affiché dans `/version` | Vide |

### Exemple `.env` minimal complet

```dotenv
IMAGE_TAG=latest
GIT_SHA=

POSTGRES_USER=rag
POSTGRES_PASSWORD=a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4
POSTGRES_DB=rag_config
DATABASE_URL=postgresql://rag:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4@postgres:5432/rag_config
RAG_POSTGRES_ADMIN_URL=postgresql://rag:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4@postgres:5432/postgres

RAG_MASTER_KEY=f3a9b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1
RAG_SESSION_SECRET=0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b
HARPOCRATE_DEK=
RAG_WEBHOOK_SECRET=

RAG_PUBLIC_URL=https://rag.example.com

RAG_BOOTSTRAP_ADMIN_USERNAME=admin
RAG_BOOTSTRAP_ADMIN_EMAIL=admin@example.com
RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH=$2b$12$XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
RAG_BOOTSTRAP_SESSION_TTL_SECONDS=28800

CADDY_HTTP_PORT=80
PRICING_FILE_HOST_PATH=./embedding_providers_pricing.yml

SYNC_WORKER_POLL_INTERVAL_SECONDS=30
SYNC_DEFAULT_INTERVAL_SECONDS=300
LOG_LEVEL=INFO
```

---

## Étape 4 — Démarrer la stack

```bash
docker compose -f docker-compose.prod.yml up -d
```

Docker va :
1. Télécharger les images depuis `ghcr.io/ag-flow/`
2. Démarrer Postgres et attendre qu'il soit prêt
3. Démarrer le backend (qui applique les migrations SQL au boot)
4. Démarrer le frontend
5. Démarrer Caddy

Vérifier que tout est `healthy` :

```bash
docker compose -f docker-compose.prod.yml ps
```

Tester le smoke check :

```bash
curl http://localhost/health
# → {"status":"ok"}

curl http://localhost/version
# → {"version":"x.y.z","git_sha":"..."}
```

---

## Étape 5 — Première connexion

Ouvrir `https://rag.example.com/ui` dans un navigateur.

Se connecter avec :
- **Nom d'utilisateur** : valeur de `RAG_BOOTSTRAP_ADMIN_USERNAME` (défaut : `admin`)
- **Mot de passe** : le mot de passe clair que vous avez fourni à l'étape 3

Depuis l'IHM, configurer OIDC (`/ui/settings/oidc-config`) si vous souhaitez
utiliser Keycloak ou un autre IdP à la place du compte local.

---

## Mises à jour

Pour déployer une nouvelle version de l'image :

```bash
# Mettre à jour IMAGE_TAG dans .env (ou utiliser latest)
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

Les migrations SQL sont appliquées automatiquement au démarrage du backend.
Pas de procédure manuelle.

---

## Sauvegardes

Les données persistantes sont dans deux volumes Docker nommés :

| Volume | Contenu |
|---|---|
| `rag_postgres_data` | Base Postgres complète |
| `rag_repos` | Clones git du sync worker (recréables, pas critiques) |

Sauvegarder Postgres :

```bash
docker exec rag-postgres pg_dumpall -U rag | gzip > rag_backup_$(date +%Y%m%d).sql.gz
```

---

## Diagnostic

```bash
# Logs en temps réel
docker compose -f docker-compose.prod.yml logs -f

# Logs d'un seul service
docker compose -f docker-compose.prod.yml logs -f backend

# État des containers
docker compose -f docker-compose.prod.yml ps

# Redémarrer un service
docker compose -f docker-compose.prod.yml restart backend
```

---

## Désactiver le compte bootstrap après configuration OIDC

Une fois OIDC configuré et testé, vider `RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH` dans `.env`
et redémarrer le backend :

```bash
# Dans .env :
RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH=

docker compose -f docker-compose.prod.yml restart backend
```

Le compte local n'est plus actif. L'accès passe exclusivement par OIDC.
