# BUG-011 — `base_url` rerank : ignorée pour cohere/voyage/jina, utilisée comme URL complète pour dashscope

**Statut : 🟢 corrigé**

- **Zone** : backend / rerank
- **Sévérité** : basse (mais implication sécurité : fuite de credentials vers l'endpoint public)
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/rerank/providers/factory.py:20-38`, `backend/src/rag/rerank/providers/dashscope.py:41`
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — honorer/rejeter base_url par provider, mécanique

## Description

`RerankSpec`/`RerankCreateSpec` acceptent `base_url` pour tous les providers, elle est persistée et passée à la factory — mais les branches cohere/voyage/jina la jettent (`_URL` codé en dur) : un endpoint proxy/self-hosted configuré est silencieusement ignoré. Pour dashscope, `base_url` sert d'URL d'endpoint **complète** (`self._url = base_url or _URL_INTERNATIONAL`), contrairement à tous les autres composants où base_url est un préfixe d'hôte.

## Scénario de défaillance

1. (a) Un admin configure le rerank jina avec `base_url=https://jina.internal.corp` (déploiement privé) → les requêtes, **clé API incluse**, partent vers `api.jina.ai` — égression silencieuse de données/credentials vers l'endpoint public.
2. (b) Un admin met dashscope `base_url=https://dashscope.aliyuncs.com` (une base, comme le nom du champ le suggère, pour passer en région CN) → le POST tape l'hôte nu, 404 → toutes les recherches échouent.

## Code concerné

```python
if provider == "jina":
    ...
    return JinaRerankProvider(model=model, api_key=api_key)   # base_url jetée
# dashscope.py :
self._url = base_url or _URL_INTERNATIONAL   # base_url doit être l'endpoint COMPLET
```

## Piste de correction

Honorer `base_url` dans cohere/voyage/jina (préfixe + path), et pour dashscope concaténer le path rerank à une base d'hôte ; ou rejeter `base_url` à la validation pour les providers qui ne le supportent pas.
