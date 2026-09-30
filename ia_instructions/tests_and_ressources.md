# Ressources attribuées — mémoire de l'agent

> Tenu à jour par l'agent à chaque ressource notifiée (ajout) ou reprise (retrait) — voir
> « Machines de test » dans `CLAUDE.md`. Ce fichier dit lesquelles tu as, ici et maintenant.

| Ressource | Accès | Rôle | Source / vérifié le |
|---|---|---|---|
| `rag-dev` | *à confirmer* (aucun alias SSH dans ce workspace au 2026-09-26) | machine de dev/test de ragflow : backend, postgres, caddy, alloy ; logs `host="rag-dev"` | logs Loki, 2026-09-26 |
| Loki / Grafana | `devpod__logs_query` (MCP) ; Grafana `http://192.168.10.164:3001` | journaux centralisés | MCP, 2026-09-26 |
| Prometheus métriques | `192.168.10.164:9090` — **injoignable** (ticket `6992b0fe`) | historisation CPU / mémoire / disque | logs Alloy, 2026-09-24 |

Aucune machine de test n'est déclarée par alias SSH (`test1`, `test2`…) dans ce workspace :
**à signaler** avant toute livraison, ne pas deviner un hôte.
