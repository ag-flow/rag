# BUG-037 — Sélecteur de job « le plus ancien » trie par UUID aléatoire : pas de FIFO, famine possible

**Statut : 🟢 corrigé**

- **Zone** : backend / sync/executor + migration
- **Sévérité** : moyenne
- **Complexité** : modérée (ajout de colonne + migration)
- **Fichiers** : `backend/src/rag/sync/executor.py:62`, `migrations/003_jobs.sql:5`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — migration de schéma + changement d'ordonnancement

## Description

`pick_next_pending_job` prétend prendre « le job pending le plus ancien » via `ORDER BY j.id`, mais `index_jobs.id` est `gen_random_uuid()` (v4, aléatoire). L'ordre est arbitraire, pas chronologique ; la table n'a pas de `created_at` de repli.

## Scénario de défaillance

Trafic webhook/push soutenu maintient ~20 jobs pending. Un job qui a un UUID à tri élevé est bypassé de façon répétée par des jobs plus récents à tri bas — un push fait il y a des heures est indexé après des pushes faits il y a des secondes, ou en charge pathologique jamais.

## Code concerné

```sql
WHERE j.status = 'pending' ... ORDER BY j.id LIMIT 1 FOR UPDATE OF j SKIP LOCKED
```

## Piste de correction

Ajouter une colonne `created_at`/séquence et `ORDER BY created_at` (retry_after-aware), ou passer à UUIDv7.
