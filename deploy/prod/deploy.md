# Déploiement production — ag-flow.rag

---

## Prérequis

| Logiciel | Version | Vérification |
|---|---|---|
| Docker Engine | 24+ | `docker --version` |
| Docker Compose (plugin) | v2.20+ | `docker compose version` |
| curl | — | `curl --version` |
| Python 3 + bcrypt | — | `python3 -c "import bcrypt"` |

Installer bcrypt si absent :
```bash
pip install bcrypt
# ou
apt-get install -y python3-bcrypt
```

---

## Première installation

### 1. Télécharger et exécuter le script de déploiement

```bash
curl -fsSL https://raw.githubusercontent.com/ag-flow/rag/main/deploy/prod/deploy.sh \
  | bash
```

Si les packages GHCR sont privés, passer un Personal Access Token (scope `read:packages`) :

```bash
curl -fsSL https://raw.githubusercontent.com/ag-flow/rag/main/deploy/prod/deploy.sh \
  | GHCR_TOKEN=ghp_votre_token bash
```

Le script :
- Vérifie que Docker et Docker Compose sont installés
- S'authentifie sur `ghcr.io` si `GHCR_TOKEN` est fourni
- Crée le répertoire `/opt/rag`
- Télécharge `docker-compose.yml`, `Caddyfile`, `pricing.yml`, `.env.example`
- Crée `/opt/rag/.env` depuis `.env.example` (si inexistant)

> **Répertoire personnalisé** : passer `DEPLOY_DIR=/chemin/voulu` avant la commande.
> ```bash
> curl -fsSL ... | DEPLOY_DIR=/srv/rag GHCR_TOKEN=ghp_... bash
> ```

#### Rendre les packages publics (alternative au token)

Dans GitHub → Package `rag-backend` → Package settings → Change visibility → Public.
Répéter pour `rag-frontend`. Les images peuvent alors être tirées sans authentification.

---

### 2. Générer les secrets

```bash
echo "POSTGRES_PASSWORD : $(openssl rand -hex 24)"
echo "RAG_MASTER_KEY    : $(openssl rand -hex 32)"
echo "RAG_SESSION_SECRET: $(openssl rand -hex 32)"
echo "HARPOCRATE_DEK    : $(openssl rand -hex 32)"
```

Conserver ces valeurs — elles ne peuvent pas être régénérées sans perte de données.

---

### 3. Générer le hash du mot de passe admin

```bash
python3 -c "
import getpass, bcrypt
pwd = getpass.getpass('Mot de passe admin : ').encode()
print(bcrypt.hashpw(pwd, bcrypt.gensalt(12)).decode())
"
```

Copier la sortie (`$2b$12$...`) pour l'étape suivante.

---

### 4. Remplir le fichier `.env`

```bash
cd /opt/rag
nano .env   # ou vim, vi...
```

Variables **obligatoires** à renseigner :

| Variable | Valeur |
|---|---|
| `POSTGRES_PASSWORD` | Secret généré à l'étape 2 |
| `RAG_MASTER_KEY` | Secret généré à l'étape 2 |
| `RAG_SESSION_SECRET` | Secret généré à l'étape 2 |
| `RAG_PUBLIC_URL` | URL externe (`https://rag.example.com`) |
| `RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH` | Hash bcrypt généré à l'étape 3 |

> **Important — hash bcrypt dans un `.env` Docker** : les `$` du hash doivent être doublés en `$$`.
> Un hash bcrypt ressemble à `$2b$12$xxx...`. Dans `.env`, écrire :
> ```
> RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH=$$2b$$12$$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/Lew...
> ```
> Cela s'applique uniquement au fichier `.env` lu par Docker Compose — pas en ligne de commande.

Variables **optionnelles** importantes :

| Variable | Rôle |
|---|---|
| `HARPOCRATE_DEK` | Chiffrement des clés API — obligatoire dès le premier coffre créé |
| `RAG_WEBHOOK_SECRET` | Signature HMAC des webhooks sortants |
| `IMAGE_TAG` | Épingler une version précise (défaut : `latest`) |

> `DATABASE_URL` et `RAG_POSTGRES_ADMIN_URL` sont construits automatiquement
> dans `docker-compose.yml` depuis `POSTGRES_USER` / `POSTGRES_PASSWORD` — ne pas
> les définir dans `.env`.

---

### 5. Démarrer la stack

```bash
cd /opt/rag
docker compose up -d
```

Docker télécharge les images depuis `ghcr.io/ag-flow/` et démarre les services
dans l'ordre : Postgres → Backend (migrations) → Frontend → Caddy.

---

### 6. Vérifier le démarrage

```bash
# État des containers
docker compose ps

# Santé de l'API
curl http://localhost/health
# → {"status":"ok"}

# Logs de démarrage
docker compose logs backend --tail=50
```

---

### 7. Première connexion

Ouvrir `https://<votre-domaine>/ui` dans un navigateur.

- **Nom d'utilisateur** : valeur de `RAG_BOOTSTRAP_ADMIN_USERNAME` (défaut : `admin`)
- **Mot de passe** : le mot de passe clair fourni à l'étape 3

---

## Mise à jour

```bash
# Re-exécuter le script pour récupérer les fichiers de config à jour
curl -fsSL https://raw.githubusercontent.com/ag-flow/rag/main/deploy/prod/deploy.sh \
  | bash
# Le .env existant est conservé intact.

# Mettre à jour les images et redémarrer
cd /opt/rag
docker compose pull
docker compose up -d
```

Les migrations SQL sont appliquées automatiquement au démarrage du backend.

---

## Épingler une version

Pour déployer une version précise plutôt que `latest` :

1. Identifier le SHA de l'image sur [GitHub Packages](https://github.com/ag-flow/rag/pkgs/container/rag-backend)
2. Dans `.env` :
   ```
   IMAGE_TAG=abc1234
   ```
3. Redémarrer :
   ```bash
   docker compose up -d
   ```

---

## Opérations courantes

```bash
# Logs en temps réel
docker compose logs -f

# Logs d'un service
docker compose logs -f backend

# Redémarrer un service
docker compose restart backend

# Arrêter la stack (données conservées)
docker compose down

# Backup de la base
docker exec rag-postgres pg_dumpall -U rag \
  | gzip > rag_backup_$(date +%Y%m%d_%H%M%S).sql.gz
```

---

## Désactiver le compte bootstrap après configuration OIDC

```bash
# Dans /opt/rag/.env :
# RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH=   ← vider la valeur

docker compose restart backend
```

---

## Structure du répertoire

```
/opt/rag/
├── docker-compose.yml      # Stack complète (images GHCR)
├── Caddyfile               # Reverse proxy HTTP
├── pricing.yml             # Tarifs providers embedding (lecture seule)
└── .env                    # Configuration — NE PAS COMMITER
```
