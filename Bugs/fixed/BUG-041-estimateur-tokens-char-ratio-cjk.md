# BUG-041 — Estimateur de tokens par ratio de caractères : les blocs atomiques CJK passent le « plafond dur » puis explosent la vraie limite provider

**Statut : 🟢 corrigé**

- **Zone** : backend / indexer/chunking
- **Sévérité** : moyenne
- **Complexité** : modérée
- **Fichiers** : `backend/src/rag/indexer/chunking/normalizer.py:93-99`, `tokens.py:38-40`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — tokenizer exact ou heuristique multilingue

## Description

`_emit_atomic` garantit « pas de troncature silencieuse » via `ceil(len/char_ratio)` avec un ratio par défaut de 4.0 calibré EN/FR. Le texte CJK, riche en emoji ou en symboles denses fait ~1 char/token (jusqu'à 4× de sous-estimation) ; le facteur de sécurité 0.8 ne couvre pas ça. Un fence atomique estimé ≤ `hard_ceiling` peut dépasser le vrai max d'input du provider.

## Scénario de défaillance

`max_input_tokens=8192` → plafond dur 6553 « tokens » = 26 212 chars autorisés pour un bloc atomique. Un fence chinois de 25 000 chars ≈ 20 000+ tokens réels → le provider renvoie HTTP 400 → mappé en `EmbeddingProviderUnreachable` (cf. BUG-042) → retries transitoires inutiles, puis le fichier empoisonne le job (cf. BUG-033).

## Code concerné

```python
def estimate(self, text: str) -> int:
    return math.ceil(len(text) / self._char_ratio)   # ~4x de sous-estimation pour le CJK
```

## Piste de correction

Le `token_char_ratio` par modèle est déjà plumé — documenter/imposer des ratios plus bas pour les modèles multilingues, ou ajouter une heuristique conservatrice, ou brancher un tokenizer exact derrière `TokenEstimator` pour la validation des blocs atomiques.
