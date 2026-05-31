# 09 — Enrichissement LLM

L'enrichissement LLM permet d'annoter automatiquement les documents lors de leur indexation, en exécutant des prompts LLM sur leur contenu et en indexant les résultats comme métadonnées.

---

## Cas d'usage typiques

- **Générer de la documentation** pour des fichiers de code source (`.cs`, `.py`, `.ts`)
- **Extraire les fonctions publiques** d'une classe ou d'un module
- **Identifier les dépendances** d'un fichier
- **Résumer** le contenu d'un document long
- **Traduire** des commentaires de code en français pour améliorer la recherche

---

## Architecture

L'enrichissement se compose de deux niveaux :

```
Bibliothèque globale de templates (partagée entre workspaces)
├── "generate-doc-csharp"    → metadata_key: "documentation"
├── "list-public-methods"    → metadata_key: "public_methods"
└── "extract-dependencies"   → metadata_key: "dependencies"

Workspace "mon-projet"
└── Trigger sur extension .cs
    ├── Prompt 1 : template "generate-doc-csharp" + LLM Claude Opus (ordre 1)
    ├── Prompt 2 : template "list-public-methods"  + LLM GPT-4o      (ordre 2)
    └── Prompt 3 : template "extract-dependencies" + LLM Claude Opus  (ordre 3)
```

---

## Créer un template de prompt

### Via l'interface

Menu de gauche → **Configuration** → **Prompts** → **+ Créer un template**

| Champ | Description | Exemple |
|---|---|---|
| **Nom** | Identifiant unique (kebab-case) | `generate-doc-csharp` |
| **Langage** | Langage de programmation ou contexte | `csharp`, `python`, `markdown` |
| **Clé de métadonnée** | Identifiant du résultat indexé | `documentation` |
| **Type de résultat** | Format de sortie attendu | `text` ou `json` |
| **Schéma JSON** | Si type=json, schéma de validation (optionnel) | `{"type":"array","items":{"type":"string"}}` |
| **Prompt** | Template de prompt avec `{content}` comme placeholder | voir ci-dessous |

### Exemples de prompts

**Documentation de code C# :**
```
Tu es un expert C#. Génère une documentation Markdown complète pour ce fichier de code.
Inclus : description générale, liste des classes/méthodes publiques avec signatures et descriptions.
Réponds UNIQUEMENT avec la documentation, sans intro ni conclusion.

CODE :
{content}
```

**Liste des fonctions publiques (retour JSON) :**
```
Analyse ce code et retourne UNIQUEMENT un tableau JSON listant les fonctions publiques.
Chaque entrée doit avoir : name (string), signature (string), description (string).
Ne retourne rien d'autre que le JSON.

CODE :
{content}
```

**Résumé en français :**
```
Résume ce document en français en 3-5 phrases claires.
Reste factuel et concis. Réponds UNIQUEMENT avec le résumé.

DOCUMENT :
{content}
```

### Via l'API

```bash
curl -X POST https://rag.votre-domaine.fr/api/admin/prompts \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "generate-doc-csharp",
    "language": "csharp",
    "metadata_key": "documentation",
    "result_type": "text",
    "prompt": "Tu es un expert C#. Génère une documentation Markdown complète pour ce fichier.\n\nCODE :\n{content}"
  }'
```

---

## Configurer les triggers par extension

Un trigger définit quels prompts sont exécutés pour les fichiers d'une extension donnée.

### Via l'interface

1. Onglet **Triggers** du workspace
2. Cliquez **+ Ajouter un trigger**
3. Sélectionnez ou tapez l'extension (ex : `.cs`, `.py`, `.ts`)
4. Ajoutez des prompts :
   - Sélectionnez un template
   - Sélectionnez un LLM (parmi ceux configurés pour ce workspace)
   - L'ordre est important — les prompts s'exécutent dans l'ordre affiché

### Via l'API

```bash
# Créer un trigger pour les fichiers .cs
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/triggers \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "extension": ".cs",
    "enabled": true
  }'

# Ajouter des prompts au trigger (remplacer {trigger_id})
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/triggers/{trigger_id}/prompts \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "uuid-du-template",
    "llm_id": "uuid-du-llm-config",
    "order_index": 1,
    "enabled": true
  }'
```

---

## Pipeline d'indexation avec enrichissement

Quand un fichier `.cs` est détecté comme modifié :

```
1. Contenu brut indexé dans pgvector
   path: "src/UserService.cs"

2. Trigger .cs activé → 3 prompts exécutés dans l'ordre :

   Prompt 1 (generate-doc-csharp → Claude Opus)
   └── Résultat indexé sous path "src/UserService.cs::documentation"

   Prompt 2 (list-public-methods → GPT-4o)
   └── Résultat indexé sous path "src/UserService.cs::public_methods"

   Prompt 3 (extract-dependencies → Claude Opus)
   └── Résultat indexé sous path "src/UserService.cs::dependencies"

3. Webhook notifié avec le détail des enrichissements
```

### Effet sur les recherches MCP

Après enrichissement, une recherche sur "comment créer un utilisateur" peut remonter :
- Le code source `src/UserService.cs` (contenu brut)
- La documentation générée `src/UserService.cs::documentation` (plus explicite)
- Les méthodes publiques `src/UserService.cs::public_methods` (structuré)

---

## Déduplication des enrichissements

Le service ne ré-exécute les prompts que si le contenu du fichier a changé :

- **Contenu identique** (même hash SHA-256) → enrichissements existants conservés, prompts sautés
- **Contenu modifié** → tous les prompts sont ré-exécutés dans l'ordre

Si un prompt retourne un résultat vide (après trim) :
- L'enrichissement existant est **supprimé** (pas de données obsolètes)
- Le job signale ce prompt comme `empty`

---

## Voir les enrichissements dans les jobs

L'historique des jobs (onglet **Jobs**) affiche le détail des enrichissements :

```
Job 550e8400... (done)
├── Fichiers changés : 3
├── Fichiers skippés : 58
└── Enrichissements :
    ├── src/UserService.cs::documentation  (done)
    ├── src/UserService.cs::public_methods (done)
    ├── src/OrderService.cs::documentation (done)
    └── src/Config.cs::dependencies        (empty — aucune dépendance trouvée)
```

---

## Configurer les langues pour les prompts

La bibliothèque de prompts supporte une sélection de langues (cultures) pour catégoriser les templates.

Pour ajouter une culture personnalisée :

```bash
curl -X POST https://rag.votre-domaine.fr/config/languages \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "vi-VN",
    "label": "Tiếng Việt"
  }'
```

Les langues pré-installées incluent : `fr-FR`, `en-US`, `de-DE`, `ja-JP`, `zh-CN`, `ar-SA`, `es-ES`, `pt-BR`, `it-IT`, `ko-KR`, `ru-RU`, et d'autres.

---

## Bonnes pratiques

### Prompts efficaces

1. **Soyez précis sur le format de sortie** : "Réponds UNIQUEMENT avec X, sans intro ni conclusion"
2. **Utilisez le placeholder `{content}`** : c'est ainsi que le contenu du fichier est injecté
3. **Testez avec des fichiers représentatifs** avant d'activer sur tout le corpus
4. **Calibrez la taille** : pour de gros fichiers, le contexte LLM peut être dépassé — découpez en prompts plus spécifiques

### Choix du LLM

| LLM | Recommandé pour |
|---|---|
| Claude Opus | Documentation détaillée, qualité maximale |
| GPT-4o | Extraction structurée JSON, bon rapport qualité/prix |
| Claude Haiku / GPT-4o Mini | Volume élevé, résumés simples |
| Ollama | Données sensibles, zéro coût |

### Performance

- Les enrichissements sont exécutés après l'indexation principale (ne bloquent pas le job)
- Avec 3 prompts sur 100 fichiers = 300 appels LLM → coût et temps à anticiper
- Activez les triggers uniquement sur les extensions pertinentes

---

## Prochaine étape

→ [10 — Authentification OIDC](10-auth-oidc.md)
