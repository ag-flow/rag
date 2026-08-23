# Backend métriques — Prometheus (LXC 116)

Historisation des ressources de la suite ag-flow : **CPU toutes les 30 s,
mémoire toutes les 60 s, espace disque toutes les 30 min**. Complète la stack
logs (Loki + Grafana) déjà en place sur le même hôte.

Topologie — identique à celle des logs, les agents poussent, le central reçoit :

```
rag-dev                                     LXC 116 (192.168.10.164)
┌────────────────────────────┐              ┌──────────────────────────┐
│ alloy                      │   logs       │ Loki        :3100        │
│  ├ exporter.unix (hôte)    │ ───────────► │                          │
│  └ exporter.cadvisor (ctn) │              │                          │
│      ↓ 3 scrape jobs       │   métriques  │ Prometheus  :9090        │
│      cpu 30s / mem 60s     │ ───────────► │  (remote-write receiver) │
│      / disk 30m            │              │                          │
└────────────────────────────┘              │ Grafana     :3001        │
                                            └──────────────────────────┘
```

Prometheus ne scrute rien à distance : il **reçoit**. Enrôler un nouvel hôte ne
demande donc aucune modification ici — seulement un `METRICS_URL` dans le `.env`
de l'hôte émetteur.

## Déploiement

Sur le LXC 116 :

```bash
mkdir -p /opt/metrics-stack
# copier docker-compose.yml et prometheus.yml de ce dossier dans /opt/metrics-stack
cd /opt/metrics-stack && docker compose up -d
curl -sf http://127.0.0.1:9090/-/ready && echo " prometheus prêt"
```

Puis la datasource Grafana :

```bash
cp grafana-datasource.yml /etc/grafana/provisioning/datasources/prometheus.yml
# (ou, si Grafana est conteneurisé, dans le volume de provisioning monté)
docker restart <conteneur-grafana>
```

Enfin, importer `../grafana/ragflow-resources-dashboard.json` dans Grafana en
sélectionnant cette datasource pour `DS_PROM`.

## Côté hôte émetteur (rag-dev)

Dans le `.env` du serveur — **à la main**, le sync de `dev-deploy.sh` ne réécrit
jamais une clé existante :

```
METRICS_URL=http://192.168.10.164:9090/api/v1/write
```

puis `docker compose -f docker-compose-dev.yml up -d alloy`.

## Vérifications

```bash
# 1. Prometheus reçoit-il ?
curl -s 'http://192.168.10.164:9090/api/v1/query?query=up' | head -c 300

# 2. Les métriques de rag-dev arrivent-elles ?
curl -s --data-urlencode 'query=node_load1{host="rag-dev"}' \
     http://192.168.10.164:9090/api/v1/query

# 3. Les trois cadences sont-elles respectées ? (écart entre deux points)
curl -s --data-urlencode 'query=count_over_time(node_load1{host="rag-dev"}[10m])' \
     http://192.168.10.164:9090/api/v1/query   # attendu ~20 (30 s)
```

## Rétention et volume

30 jours par défaut (`PROM_RETENTION`). À ~100 séries et ces cadences, l'ordre
de grandeur est de **quelques dizaines de Mo** — sans commune mesure avec les
logs, d'où une rétention plus longue que les 7 jours de Loki : un pic CPU ne
s'interprète qu'en le comparant à son historique.

## Sécurité

Le port 9090 est exposé **sans authentification** sur le réseau privé, comme
Loki (:3100) sur ce même hôte. L'accès utilisateur passe par Grafana
(`log.yoops.org`, SSO Keycloak). Ne pas publier 9090 au-delà du LAN ni via le
tunnel Cloudflare.
