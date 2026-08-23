# Observabilité ragflow — Grafana / Loki / métriques

Les conteneurs ragflow poussent leurs logs vers Loki via le collecteur **Alloy**
(service `alloy` du `docker-compose-dev.yml`, config `deploy/alloy-config.alloy`).
Labels appliqués : `job="ragflow"`, `host="$LOKI_HOSTNAME"` (défaut `rag-dev`),
`container` (nom du conteneur).

## Dashboard logs

`ragflow-dashboard.json` — dashboard minimal, importable tel quel dans le Grafana
central (`log.yoops.org` / 192.168.10.164) :

1. **Import** — Grafana → Dashboards → New → Import → *Upload JSON file*, puis
   sélectionner la datasource Loki quand c'est demandé (`DS_LOKI`).
2. Variable `host` : liste les hosts connus de Loki, défaut `rag-dev`.

### Panneaux

| Panneau | Source |
|---|---|
| Volume de logs par niveau | `level` du JSON structlog |
| Erreurs (fenêtre) | `level="error"` |
| Jobs terminés | événement `sync.executor.job_done` |
| Jobs d'indexation par statut | événement `push_job.done`, champ `status` |
| Échecs de pipeline | `*_failed` (enrichissement, persistance, rebuild lexical) |
| Activité recherche MCP | `mcp_standard.search` / `search_files` / `get_document` |
| Erreurs récentes | flux `level="error"` |

## Métriques ressources (CPU / mémoire / disque)

Le **même** conteneur `alloy` collecte aussi les ressources et les pousse en
**remote-write** vers un backend Prometheus (`METRICS_URL` dans le `.env` du
serveur ; déploiement du backend : `../metrics-stack/`). Deux sources
embarquées dans Alloy :

| Source | Portée | Métriques retenues |
|---|---|---|
| `prometheus.exporter.unix` | l'hôte | `node_cpu_seconds_total`, `node_load{1,5,15}`, `node_memory_*`, `node_filesystem_{avail,size}_bytes` |
| `prometheus.exporter.cadvisor` | chaque conteneur | `container_cpu_usage_seconds_total`, `container_cpu_cfs_throttled_seconds_total`, `container_memory_working_set_bytes`, `container_spec_memory_limit_bytes` |

### Cadences

| Famille | Intervalle | Job Alloy |
|---|---|---|
| CPU | **30 s** | `ragflow-cpu` |
| Mémoire | **60 s** | `ragflow-memory` |
| Espace disque | **30 min** | `ragflow-disk` |

Un `prometheus.scrape` ne porte qu'**un** `scrape_interval` : les trois cadences
imposent trois jobs qui scrutent les mêmes exporters, chacun ne conservant
(`keep` sur `__name__`) que sa famille. Les exporters étant in-process, le coût
des scrutations redondantes est négligeable.

Le label `container` posé sur les métriques cadvisor est **le même** que celui
des logs Loki (renommé depuis `name` par `prometheus.relabel "common"`) : un pic
CPU se corrèle directement avec les lignes de log du conteneur fautif.

### Piège — le disque à 30 min et la péremption Prometheus

Prometheus considère une série **périmée après 5 minutes** sans nouveau point.
Avec une scrutation toutes les 30 min, une requête brute sur
`node_filesystem_avail_bytes` renvoie donc du vide 25 minutes sur 30. Les
panneaux disque **doivent** envelopper la métrique :

```promql
last_over_time(node_filesystem_avail_bytes{host=~"$host"}[35m])
```

C'est ce que fait `ragflow-resources-dashboard.json`. Alternative si l'on veut
des requêtes brutes : démarrer Prometheus avec `--query.lookback-delta=35m`
(s'applique alors à **toutes** les métriques, y compris CPU et mémoire — à ne
faire qu'en connaissance de cause).

### Dashboard ressources

`ragflow-resources-dashboard.json` — import identique au dashboard logs, en
sélectionnant la datasource **Prometheus** (`DS_PROM`). Sept panneaux : CPU
hôte, CPU par conteneur, load average, mémoire hôte, mémoire par conteneur,
espace disque disponible, remplissage disque.

### Dépannage — aucune métrique n'arrive

```bash
docker exec rag-alloy printenv METRICS_URL   # doit pointer sur le backend actif
```

Puis l'UI d'Alloy (`http://<host>:12345`) → *Components* : les composants
`prometheus.scrape.*` et `prometheus.remote_write.metrics` doivent être en
état sain. `dev-deploy.sh` alerte en fin de déploiement si l'endpoint
remote-write est injoignable.

Si le CPU/la mémoire décrivent des valeurs manifestement fausses (proches de
zéro, ou identiques à celles du conteneur Alloy), ce sont les montages hôte du
service `alloy` qui manquent — `/proc:/host/proc`, `/sys:/sys`, `/:/rootfs`,
`/var/lib/docker` (cf. `docker-compose-dev.yml`).

## Limite connue (logs)

Pas de **latence de recherche** ici : le backend logge le nombre de hits, pas la
durée. Les `duration_ms` des jobs sont persistés en base (`index_jobs`), pas dans
les logs. Ajouter un `log.info("...", duration_ms=...)` côté recherche pour un
panneau de latence.

## Dépannage — aucun log n'arrive

Symptôme : `{host="rag-dev"}` vide dans Loki alors que l'app tourne.
Cause la plus fréquente : `LOKI_URL` périmé dans le `.env` du serveur (le sync de
`dev-deploy.sh` n'écrase jamais une clé existante). Vérifier :

```bash
docker exec rag-alloy printenv LOKI_URL   # doit pointer sur l'instance Loki active
```

Corriger la ligne dans le `.env` du serveur puis `docker compose up -d alloy`.
Depuis 2026-07-20, `dev-deploy.sh` émet un avertissement si Loki est injoignable
en fin de déploiement.
