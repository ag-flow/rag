# BUG-008 — `run_backfill` : le paramètre `workspace_dsn_map` est documenté mais totalement ignoré

**Statut : 🟢 corrigé**

- **Zone** : backend / maintenance
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/maintenance/backfill_enrichment_metadata.py:50-90`
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — honorer le paramètre ou le supprimer, localisé

## Description

La signature et la docstring promettent `workspace_dsn_map = {workspace_name: rag_cnx} optionnel — Si absent, interroge workspaces`. Le corps ne référence jamais `workspace_dsn_map` ; il utilise toujours `w.rag_cnx` depuis la base. Tout appelant (harnais de test, run ops contre une réplique, override de DSN pour hôtes traduits réseau) qui passe la map obtient silencieusement des connexions vers les DSN stockés en base.

## Scénario de défaillance

1. Un opérateur lance le backfill depuis l'extérieur du réseau Docker où les hôtes `rag_cnx` (ex. `postgres:5432`) ne résolvent pas, en passant `workspace_dsn_map` avec des DSN joignables comme la docstring l'y invite.
2. L'override est ignoré → erreurs de connexion (meilleur cas) ou, si les DSN stockés résolvent vers autre chose dans cet environnement, **le backfill écrit dans les mauvaises bases**.

## Code concerné

```python
async def run_backfill(
    config_dsn: str,
    workspace_dsn_map: dict[str, str] | None = None,  # jamais lu ensuite
) -> int:
    ...
    rag_cnx = row["rag_cnx"]   # toujours la valeur DB
```

## Piste de correction

Honorer la map : `dsn = (workspace_dsn_map or {}).get(row["name"], row["rag_cnx"])` lors du regroupement, ou supprimer le paramètre.
