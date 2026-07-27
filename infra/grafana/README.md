# Observabilité ragflow — Grafana / Loki

Les conteneurs ragflow poussent leurs logs vers Loki via le collecteur **Alloy**
(service `alloy` du `docker-compose-dev.yml`, config `deploy/alloy-config.alloy`).
Labels appliqués : `job="ragflow"`, `host="$LOKI_HOSTNAME"` (défaut `rag-dev`),
`container` (nom du conteneur).

## Dashboard

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

## Limite connue

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
