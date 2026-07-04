# BUG-046 — Le retry sur rate-limit ignore `Retry-After` et relance des séquences de batch complètes

**Statut : 🟢 corrigé**

- **Zone** : backend / indexer/providers
- **Sévérité** : basse
- **Complexité** : modérée
- **Fichiers** : `backend/src/rag/indexer/providers/adapter.py:53-63,109-117`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — backoff jitteré au niveau batch, logique de retry

## Description

Sur 429, l'adapter dort 2s fixes et retente une fois. Les vrais providers demandent souvent ≥10-60s (header `Retry-After`, lu nulle part). Quand l'unique retry échoue, l'exception avorte `embed_texts` ; les batches déjà embeddés dans le même appel sont jetés, et le retry au niveau job les ré-embed tous (le moteur legacy n'a pas de dédup par hash, donc ça se répète intégralement).

## Scénario de défaillance

Workspace legacy, fichier de 5 000 chunks = 50 batches OpenAI. Le batch 42 tombe sur une fenêtre de rate-limit de 60s → retry 2s échoue → job replanifié → tentative suivante ré-embed les batches 1-41, re-déclenchant le rate-limit — une boucle 429 auto-entretenue qui brûle le quota.

## Code concerné

```python
if response.status_code in (429, 503):
    if attempt == 0:
        await asyncio.sleep(self._retry_sleep)   # 2.0s fixes, Retry-After ignoré
        continue
```

## Piste de correction

Honorer `Retry-After` (plafonné), utiliser plus d'une tentative avec backoff exponentiel jitteré au niveau batch.
