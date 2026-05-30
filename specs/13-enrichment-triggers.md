# RAG Service — Déclencheurs par Extension et Enrichissement LLM

## Principe

Lors de l'indexation d'un document, le service détecte son extension de fichier et vérifie si des triggers sont configurés sur le workspace. Si oui, une série de prompts LLM est exécutée séquentiellement après l'indexation du contenu brut. Le résultat de chaque prompt est stocké sous une **clé de métadonnée nommée** et réindexé — enrichissant le RAG au-delà du contenu brut.

### Exemple

Un fichier `service.cs` est pushé dans le workspace `ag-flow-docker` :
1. Indexation du contenu brut (extension `.cs`)
2. Prompt 1 — clé `documentation` — *"Génère la doc technique"* → stocké + indexé
3. Prompt 2 — clé `public_functions` — *"Liste les fonctions publiques"* → stocké + indexé
4. Prompt 3 — clé `dependencies` — *"Identifie les dépendances"* → stocké + indexé

---

## Architecture en deux niveaux

```
Bibliothèque de prompts (globale)
├── prompt "generate-doc-csharp"   → metadata_key: "documentation"
├── prompt "list-public-functions" → metadata_key: "public_functions"
└── prompt "extract-dependencies"  → metadata_key: "dependencies"

Workspace ag-flow-docker
└── trigger .cs
    ├── prompt "generate-doc-csharp"    (ordre 1, llm: sélectionné depuis les LLM configurés)
    ├── prompt "list-public-functions"  (ordre 2, llm: sélectionné depuis les LLM configurés)
    └── prompt "extract-dependencies"  (ordre 3, llm: sélectionné depuis les LLM configurés)
```

---

## Modèle de données

### Table `prompt_templates` (globale)

```sql
CREATE TABLE prompt_templates (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name            TEXT NOT NULL UNIQUE,    -- ex: "generate-doc-csharp"
  language        TEXT NOT NULL,           -- ex: "csharp", "python"
  description     TEXT,
  metadata_key    TEXT NOT NULL,           -- clé sous laquelle le résultat est stocké
                                           -- ex: "documentation", "public_functions"
  result_type     TEXT NOT NULL DEFAULT 'text',  -- "text" | "json"
  result_schema   JSONB,                   -- JSON Schema si result_type = "json", null sinon
  prompt          TEXT NOT NULL,           -- le prompt avec placeholder {content}
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);
```

La `metadata_key` est définie sur le template — elle suit le prompt partout où il est référencé, garantissant la cohérence entre workspaces.

#### Exemple — résultat texte libre

```json
{
  "name": "generate-doc-csharp",
  "language": "csharp",
  "metadata_key": "documentation",
  "result_type": "text",
  "result_schema": null,
  "prompt": "Tu es un expert C#. Génère une documentation technique complète en Markdown.\n\nCODE :\n{content}"
}
```

#### Exemple — résultat JSON structuré

```json
{
  "name": "list-public-functions",
  "language": "csharp",
  "metadata_key": "public_functions",
  "result_type": "json",
  "result_schema": {
    "type": "array",
    "items": {
      "type": "object",
      "properties": {
        "name":        { "type": "string" },
        "signature":   { "type": "string" },
        "description": { "type": "string" },
        "returns":     { "type": "string" }
      }
    }
  },
  "prompt": "Analyse ce code C# et retourne UNIQUEMENT un tableau JSON listant les fonctions publiques.\nChaque entrée doit avoir : name, signature, description, returns.\nNe retourne rien d'autre que le JSON.\n\nCODE :\n{content}"
}
```

---

### Table `workspace_extension_triggers`

```sql
CREATE TABLE workspace_extension_triggers (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  extension     TEXT NOT NULL,          -- ex: ".cs", ".py", ".ts" (avec point)
  enabled       BOOLEAN DEFAULT true,
  created_at    TIMESTAMPTZ DEFAULT now(),
  UNIQUE(workspace_id, extension)
);
```

---

### Table `workspace_extension_trigger_prompts`

```sql
CREATE TABLE workspace_extension_trigger_prompts (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  trigger_id  UUID NOT NULL REFERENCES workspace_extension_triggers(id) ON DELETE CASCADE,
  template_id UUID NOT NULL REFERENCES prompt_templates(id),
  llm_id      UUID NOT NULL,            -- référence un LLM configuré dans l'application
  order_index INT NOT NULL,             -- ordre d'exécution, commence à 1
  enabled     BOOLEAN DEFAULT true,
  UNIQUE(trigger_id, order_index)
);
```

Le `llm_id` référence un LLM déjà configuré dans l'application (provider + modèle + clé API sélectionnée depuis Harpocrate). La sélection se fait via l'IHM parmi les LLM disponibles — chaque prompt d'un trigger peut utiliser un LLM différent pour optimiser coût vs qualité.

---

### Table `document_enrichments`

```sql
CREATE TABLE document_enrichments (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  path          TEXT NOT NULL,               -- path du document source
  template_id   UUID NOT NULL REFERENCES prompt_templates(id),
  metadata_key  TEXT NOT NULL,               -- snapshot de la clé au moment de l'exécution
  result_type   TEXT NOT NULL,               -- "text" | "json"
  result        TEXT NOT NULL,               -- résultat du prompt
  result_hash   TEXT NOT NULL,               -- SHA-256(result) pour déduplication
  llm_provider  TEXT NOT NULL,               -- snapshot du provider utilisé
  llm_model     TEXT NOT NULL,               -- snapshot du modèle utilisé
  indexed_at    TIMESTAMPTZ DEFAULT now(),
  UNIQUE(workspace_id, path, template_id)
);
```

---

## Indexation des enrichissements

Le résultat de chaque prompt est indexé dans pgvector avec un path dérivé combinant le path source et la `metadata_key` :

```
src/service.cs                          ← contenu brut
src/service.cs::documentation           ← enrichissement texte
src/service.cs::public_functions        ← enrichissement JSON sérialisé
src/service.cs::dependencies            ← enrichissement texte
```

Les chunks enrichis sont thus retrouvables via le MCP comme n'importe quel autre chunk — la `metadata_key` dans le path permet de filtrer par type d'enrichissement si besoin.

---

## Pipeline d'exécution

```
Document reçu (push ou git)
        │
        ▼
Indexation contenu brut
        │
        ▼ (indexation terminée)
Détection extension de fichier
        │
        ├── Extension sans trigger → fin, webhook notifié
        │
        └── Extension avec trigger → exécution séquentielle
                │
                ▼
          Prompt ordre 1
          ├── LLM appelé avec {content}
          ├── Résultat stocké dans document_enrichments (clé: metadata_key)
          ├── Résultat indexé dans pgvector (path::metadata_key)
          └── Hash vérifié — skip si contenu source inchangé
                │
                ▼
          Prompt ordre 2 → idem...
                │
                ▼
          Tous les prompts terminés
                │
                ▼
          Webhook notifié (payload enrichi)
```

---

## Déduplication des enrichissements

Si le contenu brut du document n'a pas changé (hash identique) :
- Les prompts ne sont **pas réexécutés**
- Les enrichissements existants sont conservés tels quels
- Le job signale les prompts comme `skipped`

Si le contenu a changé, tous les prompts sont réexécutés dans l'ordre.

---

## Résultat vide — comportement

Si le LLM retourne un résultat vide ou blank (après trim) pour un prompt :

- Le résultat vide **n'est pas indexé** — aucun chunk créé dans pgvector
- Si un enrichissement existait précédemment pour ce document + cette `metadata_key` :
  - Le chunk correspondant est **supprimé de pgvector**
  - L'entrée `document_enrichments` est **supprimée**
- Le job signale le prompt comme `empty`

```
Résultat LLM reçu
        │
        ▼
trim(result) == "" ?
        │
        ├── Non → indexation normale
        │
        └── Oui → résultat vide
                │
                ├── Enrichissement précédent existait ?
                │       │
                │       ├── Oui → supprime chunk pgvector + supprime document_enrichments
                │       └── Non → rien à faire
                │
                └── Job prompt status: "empty"
```

Ce comportement permet au LLM de signaler explicitement qu'un fichier ne nécessite pas de métadonnées pour ce prompt — sans laisser de données obsolètes dans le RAG.

---

## Payload webhook enrichi

```json
{
  "event": "indexation.completed",
  "workspace": "ag-flow-docker",
  "triggered_by": "git",
  "job_id": "uuid...",
  "status": "done",
  "files_changed": 1,
  "files_skipped": 0,
  "enrichments": [
    {
      "path": "src/service.cs",
      "metadata_key": "documentation",
      "template": "generate-doc-csharp",
      "result_type": "text",
      "status": "done"
    },
    {
      "path": "src/service.cs",
      "metadata_key": "public_functions",
      "template": "list-public-functions",
      "result_type": "json",
      "status": "done"
    },
    {
      "path": "src/service.cs",
      "metadata_key": "dependencies",
      "template": "extract-dependencies",
      "result_type": "text",
      "status": "skipped"
    },
    {
      "path": "src/utils.cs",
      "metadata_key": "public_functions",
      "template": "list-public-functions",
      "result_type": "json",
      "status": "empty",
      "previous_enrichment_deleted": true
    }
  ],
  "duration_ms": 4820,
  "finished_at": "2026-05-14T09:01:02Z"
}
```

---

## Extensions courantes

| Extension | Langage / Type |
|---|---|
| `.cs` | C# |
| `.py` | Python |
| `.ts` | TypeScript |
| `.tsx` | TypeScript React |
| `.java` | Java |
| `.md` | Markdown |
| `.json` | JSON |
| `.yaml` / `.yml` | YAML |
| `.go` | Go |
| `.rs` | Rust |

---

## API

### Bibliothèque de prompts

```
GET    /prompts                  — lister tous les templates
POST   /prompts                  — créer un template
GET    /prompts/{id}             — détail
PATCH  /prompts/{id}             — modifier
DELETE /prompts/{id}             — supprimer (erreur si référencé par un trigger actif)
```

### Triggers par workspace

```
GET    /workspaces/{name}/triggers
POST   /workspaces/{name}/triggers
PATCH  /workspaces/{name}/triggers/{trigger_id}
DELETE /workspaces/{name}/triggers/{trigger_id}

POST   /workspaces/{name}/triggers/{trigger_id}/prompts
PATCH  /workspaces/{name}/triggers/{trigger_id}/prompts/{id}
DELETE /workspaces/{name}/triggers/{trigger_id}/prompts/{id}
```

### Exemple de création

```bash
# 1. Créer le template
curl -X POST https://rag.yoops.org/prompts \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -d '{
    "name": "generate-doc-csharp",
    "language": "csharp",
    "metadata_key": "documentation",
    "result_type": "text",
    "prompt": "Tu es un expert C#. Génère une documentation complète en Markdown.\n\nCODE :\n{content}"
  }'

# 2. Créer le trigger .cs sur le workspace
curl -X POST https://rag.yoops.org/workspaces/ag-flow-docker/triggers \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -d '{
    "extension": ".cs",
    "prompts": [
      { "template_id": "uuid-generate-doc",   "llm_id": "uuid-llm-existant-1", "order_index": 1 },
      { "template_id": "uuid-list-functions", "llm_id": "uuid-llm-existant-2", "order_index": 2 }
    ]
  }'
# llm_id : identifiant d'un LLM configuré dans l'application
```
