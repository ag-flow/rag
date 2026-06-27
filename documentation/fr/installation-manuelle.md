# Installation manuelle — ag-flow.rag

Installation sans Docker, directement sur un serveur Linux Debian/Ubuntu.
Cette procédure convient aux environnements où Docker n'est pas disponible
ou n'est pas souhaité.

---

## Prérequis système

| Composant | Version | Installation |
|---|---|---|
| Python | 3.12+ | `apt-get install python3.12 python3.12-venv` |
| Node.js | 20+ | Via nvm (voir ci-dessous) |
| PostgreSQL | 16 + pgvector | Via apt (voir ci-dessous) |
| Nginx | stable | `apt-get install nginx` |
| Git | 2.40+ | `apt-get install git` |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

**Ressources recommandées** : 2 Go RAM minimum, 20 Go disque.

---

## Étape 1 — Installer les dépendances système

```bash
apt-get update && apt-get install -y \
  python3.12 python3.12-venv python3.12-dev \
  build-essential curl git nginx \
  ca-certificates gnupg lsb-release
```

### Installer Node.js 20 via nvm

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
nvm install 20
nvm use 20
node --version   # v20.x.x
```

### Installer uv (gestionnaire Python)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv --version
```

---

## Étape 2 — Installer PostgreSQL 16 avec pgvector

```bash
# Ajouter le dépôt PostgreSQL officiel
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
  | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg

echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] \
  https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
  > /etc/apt/sources.list.d/postgresql.list

apt-get update
apt-get install -y postgresql-16 postgresql-16-pgvector

# Démarrer et activer
systemctl start postgresql
systemctl enable postgresql
```

### Créer l'utilisateur et la base

```bash
sudo -u postgres psql <<'EOF'
CREATE USER rag WITH PASSWORD 'MOT_DE_PASSE_FORT';
CREATE DATABASE rag_config OWNER rag;
GRANT ALL PRIVILEGES ON DATABASE rag_config TO rag;

-- Extensions requises
\c rag_config
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;
EOF
```

Remplacer `MOT_DE_PASSE_FORT` par une valeur générée avec `openssl rand -hex 24`.

### Permettre la connexion locale

Éditer `/etc/postgresql/16/main/pg_hba.conf` pour autoriser l'utilisateur `rag` :

```
# Ajouter AVANT la ligne "local all all peer"
local   rag_config   rag   md5
host    all          rag   127.0.0.1/32   md5
```

```bash
systemctl reload postgresql
```

---

## Étape 3 — Récupérer le code source

```bash
mkdir -p /opt/rag
cd /opt/rag
git clone https://github.com/ag-flow/rag.git .
git checkout main
```

---

## Étape 4 — Configurer l'environnement

```bash
cp .env.prod.example .env
chmod 600 .env
```

Adapter les valeurs pour une installation sans Docker (les noms d'hôtes changent) :

```bash
# Postgres est en local, pas dans un container nommé "postgres"
DATABASE_URL=postgresql://rag:MOT_DE_PASSE_FORT@localhost:5432/rag_config
RAG_POSTGRES_ADMIN_URL=postgresql://rag:MOT_DE_PASSE_FORT@localhost:5432/postgres

# Secrets
RAG_MASTER_KEY=$(openssl rand -hex 32)
RAG_SESSION_SECRET=$(openssl rand -hex 32)
HARPOCRATE_DEK=$(openssl rand -hex 32)

# URL publique
RAG_PUBLIC_URL=https://rag.example.com

# Chemin réel des repos git (pas un volume Docker)
SYNC_REPOS_ROOT=/var/lib/rag/repos

# Chemin réel du fichier de pricing
# (défini dans config.py via PRICING_FILE)
```

Éditer `/opt/rag/.env` avec ces valeurs et compléter `RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH`.

---

## Étape 5 — Installer et configurer le backend

### Installer les dépendances Python

```bash
cd /opt/rag/backend
uv sync --no-dev
```

### Créer le répertoire de repos git

```bash
mkdir -p /var/lib/rag/repos
chown -R www-data:www-data /var/lib/rag  # ou l'utilisateur qui exécute le backend
```

### Copier le fichier de pricing

```bash
cp /opt/rag/embedding_providers_pricing.yml /opt/rag/backend/config/pricing.yml
mkdir -p /opt/rag/backend/config
```

Ajouter dans `.env` :
```bash
PRICING_FILE=/opt/rag/backend/config/pricing.yml
```

### Appliquer les migrations SQL

```bash
cd /opt/rag/backend
uv run python -m rag.db.migrations
```

Vérifier que toutes les migrations s'appliquent sans erreur.

### Tester le démarrage manuel

```bash
cd /opt/rag/backend
DATABASE_URL="postgresql://rag:MOT_DE_PASSE@localhost:5432/rag_config" \
RAG_MASTER_KEY="votre-master-key" \
RAG_PUBLIC_URL="http://localhost:8000" \
  uv run uvicorn rag.main:build_app --factory --host 127.0.0.1 --port 8000

# Tester dans un autre terminal
curl http://localhost:8000/health
# → {"status":"ok"}
```

---

## Étape 6 — Créer le service systemd backend

```bash
cat > /etc/systemd/system/rag-backend.service <<'EOF'
[Unit]
Description=ag-flow.rag Backend
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/rag/backend
EnvironmentFile=/opt/rag/.env
ExecStart=/opt/rag/backend/.venv/bin/uvicorn \
  rag.main:build_app \
  --factory \
  --host 127.0.0.1 \
  --port 8000 \
  --workers 1
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=rag-backend

[Install]
WantedBy=multi-user.target
EOF
```

> **Note** : le chemin de `uvicorn` dépend de l'emplacement du venv créé par `uv`. Vérifier avec :

```bash
find /opt/rag/backend -name uvicorn -type f
```

```bash
systemctl daemon-reload
systemctl enable rag-backend
systemctl start rag-backend
systemctl status rag-backend
```

---

## Étape 7 — Builder le frontend

```bash
cd /opt/rag/frontend
npm ci
npm run build
# Les assets sont générés dans dist/
```

### Déployer les assets Nginx

```bash
mkdir -p /var/www/rag/ui
cp -r /opt/rag/frontend/dist/* /var/www/rag/ui/
chown -R www-data:www-data /var/www/rag
```

---

## Étape 8 — Configurer Nginx

Créer la configuration Nginx qui reproduit le comportement du Caddyfile :

```bash
cat > /etc/nginx/sites-available/rag <<'EOF'
server {
    listen 80;
    server_name rag.example.com;  # Remplacer par votre domaine

    # API backend (FastAPI)
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    # Auth OIDC
    location /auth/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location = /me {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    # WebSocket (logs jobs streaming)
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400s;
    }

    # MCP
    location = /mcp {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    # Workspace indexation
    location /workspaces/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_read_timeout 120s;
        client_max_body_size 10m;
    }

    # Health, version, OpenAPI
    location ~ ^/(health|version|openapi\.json|docs|redoc) {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    # Frontend statique
    location /ui/ {
        alias /var/www/rag/ui/;
        try_files $uri $uri/ /ui/index.html;
        expires 1d;
        add_header Cache-Control "public, no-transform";
    }

    location = / {
        return 200 "ag-flow.rag — see /ui or /api/*";
        add_header Content-Type text/plain;
    }
}
EOF

ln -s /etc/nginx/sites-available/rag /etc/nginx/sites-enabled/rag
nginx -t
systemctl reload nginx
```

---

## Étape 9 — TLS avec Certbot (si pas de Cloudflare Tunnel)

```bash
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d rag.example.com --non-interactive --agree-tos -m admin@example.com
```

Certbot modifie automatiquement la config Nginx pour HTTPS et configure le renouvellement automatique.

---

## Étape 10 — Vérification finale

```bash
# Services actifs
systemctl status rag-backend nginx postgresql

# Test complet
curl https://rag.example.com/health
curl https://rag.example.com/version

# Logs backend en temps réel
journalctl -u rag-backend -f
```

---

## Mises à jour (installation manuelle)

```bash
cd /opt/rag

# Récupérer le nouveau code
git fetch origin
git checkout main
git pull origin main

# Mettre à jour les dépendances Python
cd backend
uv sync --no-dev

# Appliquer les nouvelles migrations
uv run python -m rag.db.migrations

# Redémarrer le backend
systemctl restart rag-backend

# Rebuilder et déployer le frontend
cd ../frontend
npm ci
npm run build
cp -r dist/* /var/www/rag/ui/

# Recharger Nginx (optionnel si les assets ont changé)
systemctl reload nginx
```

---

## Structure des processus en production

```
systemd
├── postgresql.service      (port 5432, local)
├── rag-backend.service     (port 8000, localhost uniquement)
└── nginx.service           (port 80/443, public)
```

Le backend **n'est jamais exposé directement** sur le réseau. Nginx fait l'intermédiaire.

---

## Différences avec l'installation Docker

| Aspect | Docker | Manuel |
|---|---|---|
| Isolation réseau | Réseau bridge interne | Loopback (127.0.0.1) |
| Reverse proxy | Caddy | Nginx |
| Gestion des processus | Docker restart policy | systemd |
| Volumes | Named volumes Docker | Répertoires système (`/var/lib/rag`) |
| Migrations | Auto au démarrage container | Commande `uv run python -m rag.db.migrations` |
| Mise à jour | `docker compose pull && up -d` | `git pull` + `uv sync` + `systemctl restart` |
| TLS | Cloudflare Tunnel | Certbot / Cloudflare Tunnel |
