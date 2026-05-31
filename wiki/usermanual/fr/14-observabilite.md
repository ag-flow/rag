# 14 — Observabilité

ag-flow.rag produit des logs structurés JSON et les envoie à une stack Loki + Grafana pour la surveillance et le débogage.

---

## Architecture de la collecte

```
Container ag-flow.rag (LXC 201)
        │ logs JSON structlog
        ▼
Grafana Alloy (collecteur, déployé sur chaque LXC)
        │ push via HTTP
        ▼
Loki (LXC 116 — agflow-logs)
        │ stockage 7 jours
        ▼
Grafana (LXC 116 — agflow-logs)
        │ dashboards + alertes
        ▼
https://log.yoops.org (via Cloudflare Tunnel)
```

- **Rétention :** 7 jours
- **Accès :** `https://log.yoops.org` — authentification SSO Keycloak (realm `yoops`, client `grafana`)
- **Sources :** Docker socket + journald de chaque LXC actif

---

## Accéder à Grafana

1. Allez sur `https://log.yoops.org`
2. Cliquez **Sign in with SSO**
3. Authentifiez-vous avec votre compte Keycloak (realm `yoops`)
4. Vous accédez aux dashboards

> Si vous n'avez pas accès, demandez à un administrateur Keycloak de vous attribuer le rôle approprié dans le client `grafana` du realm `yoops`.

---

## Explorer les logs du service RAG

### Via l'explorateur Loki

1. Menu gauche → **Explore**
2. Sélectionnez la source **Loki**
3. Utilisez des requêtes **LogQL** pour filtrer les logs

### Requêtes LogQL utiles

**Tous les logs du service RAG :**
```logql
{service="rag-service"}
```

**Erreurs uniquement :**
```logql
{service="rag-service"} | json | level="error"
```

**Logs d'un workspace spécifique :**
```logql
{service="rag-service"} | json | workspace="harpocrate"
```

**Jobs d'indexation terminés :**
```logql
{service="rag-service"} | json | event="sync.executor.job_done"
```

**Recherches MCP :**
```logql
{service="rag-service"} | json | event="mcp.search.workspace_done"
```

**Webhooks envoyés :**
```logql
{service="rag-service"} | json | event="webhook.dispatch.sent"
```

**Erreurs d'authentification :**
```logql
{service="rag-service"} | json | level="warning" | line_format "{{.event}}: {{.message}}"
```

---

## Événements logs importants

Le service émet des événements structurés. Voici les plus utiles pour la surveillance :

### Indexation

| Événement | Description | Champs clés |
|---|---|---|
| `sync.scheduler.scheduled` | Jobs schedulés | `count` |
| `sync.executor.job_started` | Job démarré | `workspace`, `source`, `triggered_by` |
| `sync.executor.job_done` | Job terminé avec succès | `workspace`, `files_changed`, `files_skipped`, `duration_ms` |
| `sync.executor.job_error` | Job en erreur | `workspace`, `error` |

### MCP

| Événement | Description | Champs clés |
|---|---|---|
| `mcp.search.workspace_done` | Recherche MCP effectuée | `workspace`, `hits`, `indexer` |
| `mcp_standard.search` | Recherche via nouveau endpoint MCP | `workspace`, `hits` |

### Webhooks

| Événement | Description | Champs clés |
|---|---|---|
| `webhook.dispatch.sent` | Webhook envoyé | `workspace`, `webhook_name`, `http_status` |
| `webhook.dispatch.error` | Échec envoi webhook | `workspace`, `webhook_url`, `error` |
| `git_webhook.job_created` | Push reçu, job créé | `workspace`, `source`, `job_id` |
| `git_webhook.branch_mismatch` | Push ignoré (branche non surveillée) | `workspace`, `pushed`, `expected` |

### Authentification

| Événement | Description |
|---|---|
| `mcp.auth.invalid_key` | Clé API workspace invalide |
| `source.webhook.enabled` | Webhook entrant activé sur une source |
| `source.webhook.secret_rotated` | Secret webhook pivoté |

---

## Variables de log disponibles

Chaque log JSON contient :

```json
{
  "timestamp": "2026-05-31T09:01:02.123Z",
  "level": "info",
  "event": "sync.executor.job_done",
  "logger": "rag.sync.executor",
  "workspace": "harpocrate",
  "source": "docs-principal",
  "triggered_by": "webhook",
  "files_changed": 3,
  "files_skipped": 58,
  "duration_ms": 1240
}
```

---

## Niveau de log

Contrôlez la verbosité via la variable d'environnement `LOG_LEVEL` :

| Niveau | Description |
|---|---|
| `DEBUG` | Très verbeux — détails internes, résolutions secrets, requêtes SQL |
| `INFO` | Normal — opérations principales, jobs, recherches MCP |
| `WARNING` | Alertes non bloquantes — fallbacks, connexions lentes |
| `ERROR` | Erreurs bloquantes — jobs en échec, connexions impossibles |

```bash
# Dans .env
LOG_LEVEL=INFO   # Recommandé en production
LOG_LEVEL=DEBUG  # Pour le débogage
```

---

## Surveiller les erreurs de jobs

Pour détecter rapidement les problèmes d'indexation :

```logql
# Jobs en erreur dans les dernières 24h
{service="rag-service"} | json
  | event="sync.executor.job_error"
  | line_format "{{.workspace}}/{{.source}} → {{.error}}"
```

Causes fréquentes d'erreur de job :
- **Authentification git échouée** : token expiré ou révoqué dans Harpocrate
- **Repository inaccessible** : URL incorrecte ou dépôt supprimé
- **Quota embedding dépassé** : vérifier le compte OpenAI/Voyage
- **Harpocrate inaccessible** : vérifier la connexion au coffre

---

## Tableau de bord recommandé

Créez un dashboard Grafana avec les panneaux suivants :

**Panel 1 — Jobs par statut (stat)**
```logql
sum by (status) (count_over_time({service="rag-service"} | json | event=~"sync.executor.job_.*" [$__interval]))
```

**Panel 2 — Fichiers indexés vs skippés (time series)**
```logql
sum(rate({service="rag-service"} | json | event="sync.executor.job_done" | unwrap files_changed [$__interval]))
sum(rate({service="rag-service"} | json | event="sync.executor.job_done" | unwrap files_skipped [$__interval]))
```

**Panel 3 — Recherches MCP (time series)**
```logql
count_over_time({service="rag-service"} | json | event="mcp.search.workspace_done" [$__interval])
```

**Panel 4 — Erreurs d'authentification (stat)**
```logql
count_over_time({service="rag-service"} | json | level="warning" [$__interval])
```

---

## Infrastructure de logs — Administration

### Configuration Alloy (collecteur)

Les fichiers de configuration sont dans `infra/alloy-agent/` du projet.
Alloy est déployé sur chaque LXC via `scripts/infra/`.

### Stack Logs centrale

La stack Loki + Grafana est dans `infra/logs-stack/`.
Elle tourne sur le LXC 116 (`agflow-logs`, 192.168.10.116).

### Provisionner une nouvelle instance

Pour déployer Alloy sur un nouveau LXC :
```bash
# Depuis le poste local
ssh pve "bash /opt/scripts/infra/alloy-agent/install.sh 201"
# Remplacer 201 par l'ID du LXC cible
```

---

## Prochaine étape

→ [15 — API Workspace programmatique](15-api-workspace-programmatique.md)
