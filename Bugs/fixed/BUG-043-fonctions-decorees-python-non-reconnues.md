# BUG-043 — Fonctions/méthodes Python décorées non reconnues par le CodeChunker

**Statut : 🟢 corrigé**

- **Zone** : backend / indexer/chunking
- **Sévérité** : basse
- **Complexité** : modérée
- **Fichiers** : `backend/src/rag/indexer/chunking/code_chunker.py:24,137-160`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — connaissance de la grammaire tree-sitter

## Description

Vérifié contre la vraie grammaire tree-sitter : `@decorator def foo()` parse en `decorated_definition`, qui n'est ni dans `def_kinds` (`function_definition`) ni dans `container_kinds`. Les fonctions décorées au niveau module sont fusionnées en unités `(module)` anonymes (sans scope/breadcrumb, sans section parente propre) ; les méthodes décorées dans les classes ne sont pas détectées par `_members`, donc ni élidées de la coquille de classe ni émises comme unités séparées — une classe riche en `@property` devient une grosse unité-coquille.

## Scénario de défaillance

Une codebase FastAPI (chaque route est décorée `@app.get`) indexée avec la stratégie `code` : toutes les routes finissent en chunks `(module)` indifférenciés, sans breadcrumb de symbole, réduisant à néant l'intérêt du chunking code-aware.

## Code concerné

```python
"python": _LangConfig(frozenset({"function_definition"}), frozenset({"class_definition"})),
# tree-sitter : "@decorator\ndef foo()..." → kind == "decorated_definition"
```

## Piste de correction

Déballer `decorated_definition` vers sa définition interne (tree-sitter expose un champ `definition`) dans `_is_def`/`_members`, en gardant les lignes de décorateur dans l'unité.
