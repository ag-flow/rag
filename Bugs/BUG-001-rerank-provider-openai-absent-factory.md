# BUG-001 — Provider rerank "openai" accepté par le schéma mais absent de la factory

**Statut : 🔴 à corriger**

- **Zone** : backend / rerank
- **Sévérité** : haute
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/schemas/admin.py:213`, `backend/src/rag/rerank/providers/factory.py:11-39`
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — fix localisé, une décision à trancher (retirer le literal ou implémenter le provider)

## Description

`RerankSpec.provider` est un `Literal["cohere", "openai", "voyage", "ollama", "jina", "dashscope"]`, mais `make_rerank_provider` ne gère que cohere/voyage/ollama/jina/dashscope. Aucun `OpenAIRerankProvider` n'existe dans `rerank/providers/`. Une config avec `provider="openai"` passe la validation, est persistée dans `rerank_configs`, et n'explose qu'au moment de la recherche.

## Scénario de défaillance

1. Un admin crée un workspace avec `rerank.provider="openai"` → validé OK, stocké.
2. Toute recherche MCP ultérieure sur ce workspace avec >1 hit appelle `make_rerank_provider(provider="openai", ...)`.
3. → `ValueError("unknown rerank provider: openai")` → non capturé → HTTP 500 sur **toutes** les recherches jusqu'à suppression de la config.

## Code concerné

```python
# schemas/admin.py
provider: Literal["cohere", "openai", "voyage", "ollama", "jina", "dashscope"]

# factory.py — pas de branche "openai" :
raise ValueError(f"unknown rerank provider: {provider}")
```

## Piste de correction

Soit retirer `"openai"` du Literal, soit implémenter un provider rerank OpenAI. Idéalement, valider la cohérence provider↔factory au moment de l'écriture de la config (fail-fast à la création, pas à la recherche).
