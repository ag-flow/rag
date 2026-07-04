# BUG-068 — Dédup d'enrichissement clé uniquement sur le hash de la source — un changement de prompt/LLM ne relance jamais les enrichissements

**Statut : 🔴 à corriger**

- **Zone** : backend / services/enrichments
- **Sévérité** : basse
- **Complexité** : simple
- **Confiance** : moyenne
- **Fichiers** : `backend/src/rag/services/enrichments.py:90-104`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

La condition de skip est `existing["result_hash"] == src_hash` (hash du *contenu source* — le commentaire de colonne de la migration 031 dit pourtant SHA-256(result), ce que le code contredit). Éditer le template de prompt ou changer le LLM du trigger n'a aucun effet sur les documents déjà enrichis jusqu'à ce que le fichier source lui-même change.

## Scénario de défaillance

L'admin corrige un mauvais prompt ; relance l'indexation ; tous les fichiers inchangés gardent l'ancien (mauvais) enrichissement indéfiniment.

## Code concerné

```python
if existing and existing["result_hash"] == src_hash:
    results.append({..., "status": "skipped"})
    continue
```

## Piste de correction

Inclure un hash de version prompt/template dans la clé de dédup (ex. `sha256(src + prompt)`).
