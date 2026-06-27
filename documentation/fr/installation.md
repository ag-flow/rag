# Installation — ag-flow.rag

Guide d'installation de la stack complète avec Docker Compose.

---

## Prérequis

| Logiciel | Version minimale | Vérification |
|---|---|---|
| Docker Engine | 24+ | `docker --version` |
| Docker Compose (plugin) | v2.20+ | `docker compose version` |
| Accès réseau | — | Lecture de `ghcr.io` (images publiques) |

**Ressources recommandées** :
- CPU : 2 cœurs minimum, 4 recommandés
- RAM : 2 Go minimum, 4 Go recommandés
- Disque : 20 Go minimum (base Postgres + clones git)

---

## Étape 1 — Préparer le répertoire

```bash
mkdir -p /opt/rag
cd /opt/rag
```

---

## Étape 2 — Récupérer les fichiers

Télécharger les quatre fichiers nécessaires depuis le dépôt GitHub :

```bash
# Fichier Compose production
curl -Lo docker-compose.prod.yml \
  https://raw.githubusercontent.com/ag-flow/rag/main/docker-compose.prod.yml

# Reverse proxy Caddy
curl -Lo Caddyfile \
  https://raw.githubusercontent.com/ag-flow/rag/main/Caddyfile

# Tarifs providers d'embedding (requis par le backend)
curl -Lo embedding_providers_pricing.yml \
  https://raw.githubusercontent.com/ag-flow/rag/main/embedding_providers_pricing.yml

# Template de configuration
curl -Lo .env.prod.example \
  https://raw.githubusercontent.com/ag-flow/rag/main/.env.prod.example
```

---

## Étape 3 — Générer les secrets

Générer les valeurs aléatoires requises **avant** de remplir `.env` :

```bash
# Mot de passe Postgres
echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"

# Master key (admin API)
echo "RAG_MASTER_KEY=$(openssl rand -hex 32)"

# Secret de session OIDC
echo "RAG_SESSION_SECRET=$(openssl rand -hex 32)"

# Clé de chiffrement Harpocrate (si vous utilisez des coffres de secrets)
echo "HARPOCRATE_DEK=$(openssl rand -hex 32)"
```

Noter chaque valeur — elle ne sera pas régénérée automatiquement.

---

## Étape 4 — Générer le hash du mot de passe admin

Le compte admin local (`bootstrap`) requiert un hash bcrypt du mot de passe :

```bash
python3 -c "
import getpass, bcrypt
pwd = getpass.getpass('Mot de passe admin : ').encode()
h = bcrypt.hashpw(pwd, bcrypt.gensalt(12)).decode()
print(h)
"
```

Si `bcrypt` n'est pas installé :
```bash
pip install bcrypt
# ou
apt-get install -y python3-bcrypt
```

La sortie (commence par `$2b$12$...`) sera utilisée dans `.env`.

---

## Étape 5 — Créer et remplir le fichier `.env`

```bash
cp .env.prod.example .env
chmod 600 .env
```

Ouvrir `.env` et remplir chaque variable. Variables minimales obligatoires :

```bash
# Variables à personnaliser (remplacer TOUTES les valeurs CHANGEME)

# Postgres
POSTGRES_PASSWORD=<généré à l'étape 3>
DATABASE_URL=postgresql://rag:<POSTGRES_PASSWORD>@postgres:5432/rag_config
RAG_POSTGRES_ADMIN_URL=postgresql://rag:<POSTGRES_PASSWORD>@postgres:5432/postgres

# Sécurité
RAG_MASTER_KEY=<généré à l'étape 3>
RAG_SESSION_SECRET=<généré à l'étape 3>

# URL externe (avec https:// et sans slash final)
RAG_PUBLIC_URL=https://rag.example.com

# Compte admin local
RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH=<hash bcrypt de l'étape 4>
```

Variables optionnelles importantes :

```bash
# Chiffrement secrets Harpocrate — obligatoire dès le premier coffre créé
HARPOCRATE_DEK=<généré à l'étape 3>

# Signature des webhooks sortants (recommandé)
RAG_WEBHOOK_SECRET=<openssl rand -hex 32>
```

---

## Étape 6 — Vérifier la configuration

Valider que le fichier `.env` est complet avant de démarrer :

```bash
# Vérifier les variables critiques
grep -E "^(RAG_MASTER_KEY|RAG_PUBLIC_URL|DATABASE_URL|POSTGRES_PASSWORD|RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH)=" .env
```

Aucune de ces valeurs ne doit être vide.

---

## Étape 7 — Démarrer la stack

```bash
docker compose -f docker-compose.prod.yml up -d
```

Docker va télécharger les images (`ghcr.io/ag-flow/rag-backend`, `rag-frontend`), puis démarrer les services dans l'ordre :

1. **Postgres** — démarre et attend d'être `healthy`
2. **Backend** — applique les migrations SQL au démarrage, puis démarre l'API
3. **Frontend** — démarre le serveur Nginx statique
4. **Caddy** — démarre le reverse proxy

---

## Étape 8 — Vérifier le démarrage

```bash
# Statut de tous les containers
docker compose -f docker-compose.prod.yml ps

# Logs de démarrage du backend (migrations, etc.)
docker compose -f docker-compose.prod.yml logs backend --tail=50

# Test de santé
curl http://localhost/health
# Réponse attendue : {"status":"ok"}

curl http://localhost/version
# Réponse attendue : {"version":"x.y.z","git_sha":"...","environment":"prod"}
```

Si tous les containers sont `healthy` et que `/health` répond, l'installation est réussie.

---

## Étape 9 — Première connexion

Ouvrir `https://<votre-domaine>/ui` dans un navigateur.

Se connecter avec :
- **Nom d'utilisateur** : valeur de `RAG_BOOTSTRAP_ADMIN_USERNAME` (défaut : `admin`)
- **Mot de passe** : le mot de passe en clair utilisé pour générer le hash

---

## Étape 10 — Configuration Cloudflare Tunnel (optionnel)

Si vous utilisez Cloudflare Tunnel pour exposer l'application en HTTPS :

1. Dans Cloudflare Zero Trust, créer un tunnel pointant vers `http://localhost:80` (ou `http://<ip-hote>:80`)
2. Le Caddyfile est déjà configuré avec `auto_https off` pour cet usage
3. Mettre `RAG_PUBLIC_URL` dans `.env` avec l'URL publique Cloudflare

---

## Mise à jour

Pour déployer une nouvelle version :

```bash
cd /opt/rag

# Télécharger les nouvelles images
docker compose -f docker-compose.prod.yml pull

# Redémarrer avec les nouvelles images (rolling restart)
docker compose -f docker-compose.prod.yml up -d
```

Les migrations SQL sont appliquées automatiquement au démarrage du nouveau backend. Aucune intervention manuelle n'est nécessaire.

---

## Sauvegardes

### Backup de la base Postgres

```bash
# Dump complet (toutes les bases, y compris les bases workspace)
docker exec rag-postgres pg_dumpall -U rag | gzip \
  > /opt/backups/rag_backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Restauration
zcat /opt/backups/rag_backup_YYYYMMDD_HHMMSS.sql.gz \
  | docker exec -i rag-postgres psql -U rag postgres
```

### Volumes importants

| Volume Docker | Contenu | Criticité |
|---|---|---|
| `rag_postgres_data` | Base Postgres complète | **Critique** — sauvegarder |
| `rag_repos` | Clones git locaux | Faible — recréables automatiquement |
| `rag_caddy_data` | Certificats Caddy | Faible — si Cloudflare Tunnel est utilisé |

### Backup automatique (cron)

```bash
# /etc/cron.d/rag-backup
0 3 * * * root docker exec rag-postgres pg_dumpall -U rag | gzip \
  > /opt/backups/rag_backup_$(date +\%Y\%m\%d).sql.gz && \
  find /opt/backups -name "rag_backup_*.sql.gz" -mtime +30 -delete
```

---

## Désinstallation

```bash
# Arrêter et supprimer les containers
docker compose -f docker-compose.prod.yml down

# Supprimer aussi les volumes (IRRÉVERSIBLE — perte des données)
docker compose -f docker-compose.prod.yml down -v

# Supprimer les images
docker rmi ghcr.io/ag-flow/rag-backend ghcr.io/ag-flow/rag-frontend
```
