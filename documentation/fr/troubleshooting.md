# Troubleshooting — ag-flow.rag

---

## Diagnostics de base

Avant toute investigation, collecter ces informations :

```bash
# État des containers
cd /opt/rag && docker compose ps

# Santé de l'API
curl -s http://localhost/health | python3 -m json.tool

# Logs récents (tous les services)
cd /opt/rag && docker compose logs --tail=100

# Logs d'un service spécifique
cd /opt/rag && docker compose logs backend --tail=100
cd /opt/rag && docker compose logs postgres --tail=50
cd /opt/rag && docker compose logs caddy --tail=50
```

---

## Problèmes au démarrage

### Le backend ne démarre pas — erreur de migration

**Symptôme** : `docker compose ps` montre le backend en `Exit 1`.

```bash
cd /opt/rag && docker compose logs backend | grep -i "error\|migration\|fatal"
```

**Causes fréquentes** :

| Message | Cause | Solution |
|---|---|---|
| `could not connect to server` | Postgres pas encore prêt | Attendre 30s, relancer `up -d` |
| `password authentication failed` | `POSTGRES_PASSWORD` incohérent entre `.env` et `DATABASE_URL` | Vérifier que les deux valeurs correspondent |
| `database "rag_config" does not exist` | Base non créée | Postgres n'a pas été initialisé — vérifier le volume `rag_postgres_data` |
| `relation "X" already exists` | Migration partiellement appliquée | Voir section [Migrations corrompues](#migrations-corrompues) |

### Le container Postgres ne démarre pas

```bash
cd /opt/rag && docker compose logs postgres
```

**Cause fréquente** : le volume `rag_postgres_data` existe déjà avec un `POSTGRES_USER` différent.

```bash
# Vérifier le contenu du volume
docker run --rm -v rag_postgres_data:/data alpine ls /data/global/

# Solution : supprimer le volume (PERTE DE DONNÉES)
cd /opt/rag && docker compose down -v
cd /opt/rag && docker compose up -d
```

### Caddy ne démarre pas — port 80 occupé

```bash
cd /opt/rag && docker compose logs caddy
# "listen tcp :80: bind: address already in use"
```

**Solution** : identifier et arrêter le processus qui occupe le port 80.

```bash
ss -tlnp | grep :80
# ou
fuser 80/tcp
```

Si le port est définitivement occupé, changer `CADDY_HTTP_PORT` dans `.env` :

```bash
CADDY_HTTP_PORT=8080
```

Puis mettre à jour Cloudflare Tunnel pour pointer sur le nouveau port.

---

## Problèmes d'authentification

### 401 Unauthorized sur `/api/admin/*`

**Cause** : le header `Authorization: Bearer` est absent ou la valeur ne correspond pas à `RAG_MASTER_KEY`.

```bash
# Vérifier la master key configurée (affiche uniquement les premiers chars)
docker exec rag-backend env | grep RAG_MASTER_KEY | cut -c1-30
```

Tester avec la bonne valeur :

```bash
curl -H "Authorization: Bearer <votre-master-key>" http://localhost/api/admin/workspaces
```

### Impossible de se connecter à l'IHM (page blanche ou erreur OIDC)

**Vérifier** :

```bash
# OIDC configuré ?
curl -s http://localhost/api/auth/methods | python3 -m json.tool
```

Si `oidc_configured: false` et `bootstrap_enabled: false`, aucune méthode de connexion n'est active. Il faut remettre un hash bcrypt dans `RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH`.

**Vérifier `RAG_PUBLIC_URL`** : l'URL doit correspondre exactement à l'URL du navigateur (scheme + domaine), sans slash final. Une incohérence casse le callback OIDC.

### Hash bcrypt rejeté à la connexion

Regénérer le hash en s'assurant d'utiliser exactement le même mot de passe :

```bash
python3 -c "
import bcrypt
# Tester si le hash est correct
password = b'votre-mot-de-passe'
stored_hash = b'\$2b\$12\$...'  # hash depuis .env
print(bcrypt.checkpw(password, stored_hash))
"
```

Si `False`, le hash ne correspond pas au mot de passe. Regénérer :

```bash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'nouveau-mdp', bcrypt.gensalt(12)).decode())"
```

Mettre à jour `.env` puis redémarrer :

```bash
cd /opt/rag && docker compose restart backend
```

---

## Problèmes d'indexation

### Les jobs restent en `pending` indéfiniment

Le worker asynchrone n'est pas en cours d'exécution ou est bloqué.

```bash
cd /opt/rag && docker compose logs backend | grep "sync_worker\|worker"
```

**Causes fréquentes** :

1. **Circuit breaker ouvert** : vérifier via l'API.

```bash
curl -H "Authorization: Bearer <master-key>" \
  http://localhost/api/admin/workspaces/<name>/circuit-breaker
```

Si `"status": "open"`, le provider d'embedding est en erreur. Voir [Circuit breaker ouvert](#circuit-breaker-ouvert).

2. **Worker crashé** : le backend a redémarré et le worker est dans un état incohérent.

```bash
cd /opt/rag && docker compose restart backend
```

3. **`retry_after` dans le futur** : un job transient a été planifié pour un retry différé. C'est le comportement attendu — attendre l'expiration.

### Les jobs échouent avec `error`

```bash
# Voir le message d'erreur du job
curl -H "Authorization: Bearer <master-key>" \
  http://localhost/api/admin/workspaces/<name>/jobs
```

| Message | Cause | Solution |
|---|---|---|
| `Quota exhausted: HTTP 402` | Crédit provider épuisé | Recharger le compte, fermer le circuit |
| `401 Unauthorized` | Clé API provider invalide | Vérifier la clé dans Harpocrate |
| `Connection refused` | Provider inaccessible (Ollama off) | Vérifier que le service est démarré |
| `push_job_payloads not found` | Payload expiré (job ancien) | Créer un nouveau job push |
| `Repository not found` | URL git incorrecte ou droits insuffisants | Vérifier le credential git |

### Circuit breaker ouvert

```bash
# Vérifier l'état
curl -H "Authorization: Bearer <master-key>" \
  http://localhost/api/admin/workspaces/<name>/circuit-breaker
```

**Résolution** :

1. Identifier la cause dans `error_message`
2. Corriger le problème (recharger le compte, corriger la clé API)
3. Fermer manuellement le circuit :

```bash
curl -X POST -H "Authorization: Bearer <master-key>" \
  http://localhost/api/admin/workspaces/<name>/circuit-breaker/close
```

Le circuit se referme aussi automatiquement après l'expiration du TTL (`open_until`).

### Les fichiers git ne sont pas re-indexés

**Vérifier la déduplication** : si le contenu d'un fichier n'a pas changé, il est skippé (comportement normal). Voir le job :

```bash
curl -H "Authorization: Bearer <master-key>" \
  "http://localhost/api/admin/workspaces/<name>/jobs/<job_id>/files"
```

Si `status: "skipped"`, le fichier est identique à la version indexée. Pour forcer la réindexation :

```bash
curl -X POST -H "Authorization: Bearer <master-key>" \
  http://localhost/api/admin/workspaces/<name>/reindex
```

**Vérifier les patterns `include`/`exclude`** de la source git :

```bash
curl -H "Authorization: Bearer <master-key>" \
  http://localhost/api/admin/workspaces/<name>/sources
```

Si le fichier ne correspond à aucun pattern `include`, il est ignoré.

---

## Problèmes de connexion aux sources git

### `test-connection` échoue avec `Repository not found`

```bash
curl -X POST -H "Authorization: Bearer <master-key>" \
  http://localhost/api/admin/workspaces/<name>/sources/<source_id>/test-connection
```

**Causes** :

| Cas | Diagnostic | Solution |
|---|---|---|
| Dépôt privé, token manquant | `auth_ref` vide ou clé absente dans Harpocrate | Ajouter le credential git |
| Token expiré | Message `401` de GitHub | Renouveler le token |
| Mauvaise URL | `404` de GitHub | Vérifier l'URL et le nom du dépôt |
| Clé SSH non déposée | `Permission denied (publickey)` | Ajouter la clé publique comme deploy key |

### La clé SSH générée n'est pas acceptée par GitHub

1. Récupérer la clé publique :

```bash
curl -H "Authorization: Bearer <master-key>" \
  http://localhost/api/admin/ssh-keys/all
```

2. Copier la valeur `public_key`
3. L'ajouter dans GitHub → Settings → Deploy keys du dépôt

Vérifier que la clé logique (`logical_name`) dans Harpocrate correspond exactement à `auth_ref` dans la config de la source.

---

## Problèmes de performance

### Indexation très lente

**Vérifier le nombre de workers actifs** et l'intervalle de polling :

```bash
docker exec rag-backend env | grep SYNC_WORKER_POLL_INTERVAL_SECONDS
```

Valeur recommandée en prod : `30` (secondes entre deux passages du worker).

**Vérifier la charge Postgres** :

```bash
docker exec rag-postgres psql -U rag -c "SELECT count(*) FROM index_jobs WHERE status='running';"
```

Si plusieurs jobs `running` existent depuis longtemps, le backend a peut-être crashé mid-job. Redémarrer le backend pour libérer les verrous.

### La recherche MCP retourne des résultats vides

1. Vérifier que des documents sont indexés :

```bash
curl -H "Authorization: Bearer <master-key>" \
  http://localhost/api/admin/workspaces/<name>/index-keys
```

2. Si la liste est vide, déclencher une sync ou un push.

3. Vérifier le `min_score` de la requête : abaisser à `0.5` pour voir si des résultats apparaissent avec un score plus faible.

4. Vérifier que le provider d'embedding de la requête MCP correspond à celui utilisé lors de l'indexation.

---

## Problèmes de base de données

### Migrations corrompues

Si une migration a échoué à mi-chemin, la base peut être dans un état incohérent.

```bash
# Voir les migrations appliquées
docker exec rag-postgres psql -U rag -d rag_config \
  -c "SELECT version, applied_at FROM schema_migrations ORDER BY version;"
```

**En cas de doute** : restaurer depuis un backup et réappliquer.

### Espace disque insuffisant

```bash
# Taille du volume Postgres
docker system df -v | grep rag_postgres_data

# Espace disque hôte
df -h
```

Si le disque est plein, les écritures Postgres échouent silencieusement. Libérer de l'espace ou augmenter le volume.

### Connexions Postgres épuisées

```bash
docker exec rag-postgres psql -U rag -c \
  "SELECT count(*) FROM pg_stat_activity WHERE state='active';"
```

Si le nombre est élevé, redémarrer le backend pour libérer les connexions idle.

---

## Problèmes Harpocrate

### `503 Service Unavailable` à la création d'un workspace

Harpocrate n'est pas joignable ou n'a pas de coffre configuré.

```bash
# Vérifier qu'un coffre existe
curl -H "Authorization: Bearer <master-key>" \
  http://localhost/api/admin/harpocrate-vaults
```

Si la liste est vide, créer un coffre avant de créer des workspaces.

### Résolution d'une clé logique échoue

```bash
cd /opt/rag && docker compose logs backend | grep "VaultLookupFailed"
```

La clé logique référencée (ex: `openai_embedding_key`) n'existe pas dans le coffre Harpocrate.

Vérifier les clés disponibles :

```bash
curl -H "Authorization: Bearer <master-key>" \
  "http://localhost/api/admin/harpocrate-vaults/<vault_id>/provider-keys"
```

La `logical_name` doit correspondre exactement à la référence utilisée dans la config workspace.

---

## Commandes utiles

```bash
# Redémarrer uniquement le backend (sans arrêter Postgres)
cd /opt/rag && docker compose restart backend

# Forcer le re-téléchargement des images
cd /opt/rag && docker compose pull
cd /opt/rag && docker compose up -d

# Accéder à Postgres directement
docker exec -it rag-postgres psql -U rag -d rag_config

# Voir toutes les variables d'environnement du backend
docker exec rag-backend env | sort

# Vider les logs Docker (libérer de l'espace)
docker system prune --volumes  # ATTENTION : supprime les volumes non utilisés

# Voir l'utilisation des ressources en temps réel
docker stats rag-backend rag-postgres
```
