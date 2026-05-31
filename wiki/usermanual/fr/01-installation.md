# 01 — Installation

## Prérequis

### Système

| Composant | Version minimale | Notes |
|---|---|---|
| Docker | 24.0+ | Docker Engine ou Docker Desktop |
| Docker Compose | v2.20+ | Inclus dans Docker Desktop |
| PostgreSQL | 16 | Avec extension `pgvector` |
| Mémoire RAM | 2 Go min | 4 Go recommandé pour embedding local |
| Espace disque | 5 Go min | Plus selon taille des corpus |

> **Note :** PostgreSQL avec pgvector peut être le même serveur que vos autres bases ou un serveur dédié. L'image officielle `pgvector/pgvector:pg16` inclut l'extension.

### Réseau

- Le service doit être accessible depuis l'extérieur (OIDC callback, webhooks GitHub)
- Un nom de domaine avec HTTPS est recommandé en production
- Les ports utilisés par défaut : `8000` (service RAG)

---

## Structure des fichiers

```
ag-flow.rag/
├── backend/                  ← Code Python (FastAPI)
├── frontend/                 ← Code React (Vite)
├── docker-compose.yml        ← Stack dev (postgres + redis)
├── docker-compose.prod.yml   ← Stack production complète
├── .env.example              ← Template variables d'environnement
└── scripts/
    ├── deploy.sh             ← Déploiement LXC/Docker
    └── infra/                ← Scripts Proxmox
```

---

## Variables d'environnement

Créez un fichier `.env` à la racine du projet en copiant `.env.example` :

```bash
cp .env.example .env
```

### Variables obligatoires

| Variable | Description | Exemple |
|---|---|---|
| `DATABASE_URL` | PostgreSQL — base de configuration | `postgresql://rag:monpass@postgres:5432/rag_config` |
| `RAG_POSTGRES_ADMIN_URL` | PostgreSQL — connexion admin (pour créer les bases pgvector) | `postgresql://rag:monpass@postgres:5432/postgres` |
| `RAG_MASTER_KEY` | Token Bearer pour l'API d'administration (≥32 caractères) | `mk_$(openssl rand -hex 16)` |
| `RAG_PUBLIC_URL` | URL publique du service (utilisée pour les redirections OIDC) | `https://rag.votre-domaine.fr` |

> **Sécurité :** `RAG_MASTER_KEY` est le mot de passe maître du service. Gardez-le secret et changez-le régulièrement. Minimum 32 caractères alphanumériques.

### Variables recommandées

| Variable | Défaut | Description |
|---|---|---|
| `ENVIRONMENT` | `dev` | `dev` / `staging` / `prod` — affecte la sécurité des cookies |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `HARPOCRATE_DEK` | absent | Passphrase pgcrypto pour chiffrer les clés API (≥32 chars). **Requis dès la création du premier coffre Harpocrate** |
| `RAG_SESSION_SECRET` | fallback sur master key | Secret de signature des cookies OIDC (≥32 chars) |
| `RAG_WEBHOOK_SECRET` | absent | Secret HMAC pour signer les payloads webhook sortants |
| `SYNC_WORKER_POLL_INTERVAL_SECONDS` | `30` | Fréquence de scrutation des sources git (secondes) |
| `SYNC_DEFAULT_INTERVAL_SECONDS` | `300` | Intervalle par défaut entre deux syncs d'une même source (secondes, min 60) |
| `SYNC_REPOS_ROOT` | `/var/lib/rag/repos` | Répertoire de stockage des clones git locaux |

### Bootstrap admin local (optionnel)

Ces variables créent un compte administrateur local pour les premiers accès (avant OIDC) :

| Variable | Description |
|---|---|
| `RAG_BOOTSTRAP_ADMIN_USERNAME` | Nom d'utilisateur admin local (défaut : `admin`) |
| `RAG_BOOTSTRAP_ADMIN_EMAIL` | Email de l'admin local (défaut : `admin@rag.io`) |
| `RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH` | Hash bcrypt du mot de passe. Si vide, le service génère un mot de passe aléatoire affiché dans les logs au démarrage |

### Exemple `.env` complet pour la production

```bash
# Base de données
DATABASE_URL=postgresql://rag:MonMotDePasseDB@postgres:5432/rag_config
RAG_POSTGRES_ADMIN_URL=postgresql://rag:MonMotDePasseDB@postgres:5432/postgres

# Sécurité
RAG_MASTER_KEY=mk_7f3a9c2e1b8d4f6a0e5c7b9d2f4a8e3c
RAG_PUBLIC_URL=https://rag.votre-domaine.fr
HARPOCRATE_DEK=une_passphrase_tres_longue_et_secrete_au_moins_32_chars_svp
RAG_SESSION_SECRET=another_very_long_session_secret_hex_32chars_minimum
RAG_WEBHOOK_SECRET=webhook_hmac_secret_key_pour_signer_payloads

# Comportement
ENVIRONMENT=prod
LOG_LEVEL=INFO
SYNC_REPOS_ROOT=/var/lib/rag/repos
SYNC_DEFAULT_INTERVAL_SECONDS=300

# Bootstrap admin local (à supprimer après config OIDC)
RAG_BOOTSTRAP_ADMIN_USERNAME=admin
RAG_BOOTSTRAP_ADMIN_EMAIL=admin@votre-domaine.fr
# Laisser vide = mot de passe auto-généré dans les logs
RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH=
```

---

## Installation avec Docker Compose

### Option A — Développement local

Utilise le `docker-compose.yml` qui démarre uniquement PostgreSQL et Redis.
Le service RAG tourne sur votre machine locale avec `uv`.

```bash
# Démarrer la base de données
docker compose up -d

# Démarrer le backend
cd backend
uv sync
uv run uvicorn agflow.main:app --reload --port 8000

# Démarrer le frontend
cd frontend
npm install
npm run dev  # Lance sur :5173 avec proxy /api → :8000
```

### Option B — Stack complète Docker

Utilise `docker-compose.prod.yml` pour une stack complète containerisée.

```bash
# Construire les images
docker compose -f docker-compose.prod.yml build

# Démarrer la stack
docker compose -f docker-compose.prod.yml up -d

# Vérifier que tout tourne
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs rag-service --tail=50
```

### Option C — Déploiement LXC (Proxmox)

Si vous utilisez Proxmox, le script `scripts/deploy.sh` automatise le déploiement sur un LXC :

```bash
# Depuis le poste local, déployer sur le LXC 303
./scripts/remote-deploy.ps1 303
```

---

## Vérification du démarrage

Après démarrage, vérifiez que le service répond :

```bash
# Health check
curl http://localhost:8000/health

# Réponse attendue
{
  "status": "healthy",
  "database": "connected",
  "version": "1.0.0"
}
```

```bash
# Readiness check (service prêt à traiter des requêtes)
curl http://localhost:8000/health/readiness
```

---

## Migrations de base de données

Les migrations SQL sont appliquées **automatiquement au démarrage** du service. Vous n'avez rien à faire manuellement.

Pour les appliquer manuellement (développement) :

```bash
cd backend
uv run python -m agflow.db.migrations
```

Les fichiers de migration sont dans `backend/migrations/` et sont numérotés séquentiellement (`001_init.sql`, `002_workspace_sources.sql`, etc.).

---

## Mise à jour

```bash
# Récupérer la dernière version
git pull origin main

# Reconstruire et redémarrer
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d --force-recreate

# Vérifier les logs
docker compose -f docker-compose.prod.yml logs rag-service --follow
```

> Les migrations sont automatiquement appliquées au redémarrage.

---

## Prochaine étape

→ [02 — Première configuration](02-premiere-configuration.md)
