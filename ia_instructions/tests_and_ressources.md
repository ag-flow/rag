# Ressources attribuées — mémoire de l'agent

> Tenu à jour par l'agent à chaque ressource notifiée (ajout) ou reprise (retrait) — voir
> « Machines de test » dans `CLAUDE.md`. Ce fichier dit lesquelles tu as, ici et maintenant.

| Ressource | Accès | Rôle | Source / vérifié le |
|---|---|---|---|
| `rag-dev` | *à confirmer* (aucun alias SSH dans ce workspace au 2026-09-26) | machine de dev/test de ragflow : backend, postgres, caddy, alloy ; logs `host="rag-dev"` | logs Loki, 2026-09-26 |
| Loki / Grafana | `devpod__logs_query` (MCP) ; Grafana `http://192.168.10.164:3001` | journaux centralisés | MCP, 2026-09-26 |
| Prometheus métriques | `192.168.10.164:9090` — **injoignable** (ticket `6992b0fe`) ; annoncé déployé par l'utilisateur le 2026-10-18, mais `connection refused` toujours à 10:41 UTC (Alloy rag-dev + curl `/-/ready`) — adresse réelle à confirmer | historisation CPU / mémoire / disque | logs Alloy + curl, 2026-10-18 |

Aucune machine de test n'est déclarée par alias SSH (`test1`, `test2`…) dans ce workspace :
**à signaler** avant toute livraison, ne pas deviner un hôte.
