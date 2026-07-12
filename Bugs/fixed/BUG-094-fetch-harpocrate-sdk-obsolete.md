# BUG-094 — `fetch-harpocrate-sdk.sh` obsolète : télécharge un wheel 0.4.0 que plus rien ne consomme (SDK vendoré en source)

**Statut : 🟢 corrigé**

- **Zone** : infra / backend/scripts
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `backend/scripts/fetch-harpocrate-sdk.sh:18,24`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`backend/pyproject.toml:112` référence désormais `harpocrate = { path = "vendor/harpocrate-sdk", editable = true }` (source vendorée, le wheel a été retiré — cf. commentaire pyproject:110 et Dockerfile:22-24 qui parle de v0.6.0). Le script télécharge encore `harpocrate-0.4.0-py3-none-any.whl` dans `vendor/` et son en-tête prétend qu'il est « utilisé … au build Docker », ce qui est faux.

## Scénario de défaillance

Un dev suit la doc du script avant `uv sync` → dépose un wheel 0.4.0 inutilisé dans `vendor/`, qui se retrouve embarqué dans l'image via `COPY vendor /app/vendor`, et croit à tort avoir mis à jour le SDK (version réellement utilisée : 0.6.0 source).

## Code concerné

```
WHEEL_NAME="harpocrate-0.4.0-py3-none-any.whl"
...
curl -fsSL "$HARPOCRATE_URL/v1/sdk/python-wheel" -o "$VENDOR_DIR/$WHEEL_NAME"
```

## Piste de correction

Supprimer le script ou le reconvertir en « refresh du vendored source » ; au minimum corriger l'en-tête et la version.

## Correction appliquée

Suppression du script (`backend/scripts/fetch-harpocrate-sdk.sh`) plutôt qu'une
réécriture : le SDK est désormais entièrement vendoré en source
(`backend/vendor/harpocrate-sdk/`, install éditable via `[tool.uv.sources]`),
consommé uniquement par `uv sync` — aucun code (Dockerfile, CI, pyproject) ne
télécharge plus de wheel. Réécrire le script en « refresh du vendored source »
aurait signifié inventer un nouveau workflow de synchronisation non spécifié
et sans consommateur, ce qui dépasse le fix documenté ici. La seule référence
vivante restante (`backend/README.md`) a été corrigée pour refléter le flux
réel (`uv sync` seul).
