# Design — Déclencheurs par Extension et Enrichissement LLM (spec 13)

**Date :** 2026-05-30
**Statut :** validé

## Contexte

Après l'indexation d'un document, le service détecte son extension et exécute séquentiellement des prompts LLM configurés par workspace. Chaque résultat est stocké dans `document_enrichments` et réindexé dans pgvector sous le path `{path}::{metadata_key}`. Les migrations 031 (tables) sont déjà appliquées.

---

## Jalon 1 — Backend

### Pipeline d'exécution

Injection dans `_execute_git_job` et `_execute_push_job` (`sync/executor.py`), après chaque `index_file` pour les fichiers non-skippés :

1. Extraire l'extension du fichier (`pathlib.Path(path).suffix`)
2. Charger les trigger prompts actifs `(workspace_id, extension)` avec leurs LLM configs (JOIN `workspace_extension_trigger_prompts → workspace_extension_triggers → workspace_llm_configs`)
3. Pour chaque prompt dans l'ordre (`order_index`) :
   a. Vérifier `result_hash` dans `document_enrichments` (SHA-256 du contenu source) → si inchangé → skip
   b. Appeler `call_llm()` depuis `services/llm_clients.py` avec `{content}` substitué dans le template
   c. Si résultat vide (`trim == ""`) → `_cleanup_enrichment()` → suppression pgvector + suppression `document_enrichments`
   d. Sinon → upsert `document_enrichments` + embed + upsert pgvector au path `{path}::{metadata_key}`
4. Lors de suppression d'un fichier source → `_cleanup_enrichment()` pour tous ses enrichissements

Le webhook `dispatch_webhooks` reçoit un champ `enrichments: list[{path, metadata_key, template, result_type, status}]` ajouté au payload.

### API CRUD

**Bibliothèque globale** — auth `require_master_key_or_authenticated_admin` :

```
GET    /api/admin/prompts           → list[PromptTemplateOut]
POST   /api/admin/prompts           → PromptTemplateOut (201)
GET    /api/admin/prompts/{id}      → PromptTemplateOut
PATCH  /api/admin/prompts/{id}      → PromptTemplateOut
DELETE /api/admin/prompts/{id}      → 204 / 409 si référencé
```

**Triggers par workspace** — même auth :

```
GET    /api/admin/workspaces/{name}/triggers
POST   /api/admin/workspaces/{name}/triggers
PATCH  /api/admin/workspaces/{name}/triggers/{id}      → toggle enabled
DELETE /api/admin/workspaces/{name}/triggers/{id}

GET    /api/admin/workspaces/{name}/triggers/{id}/prompts
POST   /api/admin/workspaces/{name}/triggers/{id}/prompts
PATCH  /api/admin/workspaces/{name}/triggers/{id}/prompts/{pid}
DELETE /api/admin/workspaces/{name}/triggers/{id}/prompts/{pid}
```

### Schemas (`schemas/enrichments.py`)

```
PromptTemplateCreate   name, language, description, metadata_key, result_type, result_schema, prompt
PromptTemplatePatch    description, prompt, result_schema (tous optionnels)
PromptTemplateOut      id, name, language, description, metadata_key, result_type, result_schema, prompt, created_at, updated_at

TriggerCreate          extension, enabled
TriggerPatch           enabled
TriggerOut             id, extension, enabled, prompts_count, created_at

TriggerPromptCreate    template_id, llm_id, order_index, enabled
TriggerPromptPatch     enabled, order_index
TriggerPromptOut       id, template_id, template_name, llm_id, llm_provider, llm_model, order_index, enabled
```

### Service `services/enrichments.py`

```python
async def run_enrichments(
    conn, pool_registry, *,
    workspace_id, workspace_name, path, content, rag_cnx,
    embedding_provider,
) -> list[EnrichmentResult]:
    """Exécute les trigger prompts pour l'extension de `path`."""

async def _index_enrichment(ws_pool, *, path, metadata_key, result, embedding_provider) -> None:
    """Embed + upsert pgvector au path `{path}::{metadata_key}`."""

async def _cleanup_enrichment(
    conn, ws_pool, *, workspace_id, path, template_id
) -> None:
    """Supprime document_enrichments + chunk pgvector correspondant."""
```

### Service `services/prompt_templates.py`

CRUD autonome, miroir du pattern `llm_configs.py`.

### Service `services/triggers.py`

CRUD autonome : list/create/patch/delete triggers + trigger_prompts.

### Fichiers backend

```
backend/src/rag/schemas/enrichments.py   — DTOs
backend/src/rag/services/enrichments.py  — moteur d'enrichissement
backend/src/rag/services/prompt_templates.py — CRUD prompt_templates
backend/src/rag/services/triggers.py     — CRUD triggers + trigger_prompts
backend/src/rag/api/enrichments.py       — routers admin prompts + triggers
backend/src/rag/sync/executor.py         — injection enrichissements
backend/src/rag/services/webhook_dispatch.py — enrichissements dans payload
```

---

## Jalon 2 — Frontend

### Nouvelle page `PromptsPage.tsx`

Accessible depuis la sidebar (rôle `rag-admin`). Tableau :

| Nom | Langage | metadata_key | Type | Description | Actions |
|-----|---------|--------------|------|-------------|---------|

Bouton **+ Nouveau prompt** → `AddPromptDialog.tsx` :
- Nom, langage (texte libre), metadata_key
- result_type : radio text/json
- prompt : textarea avec placeholder `{content}`
- description (optionnel)

### Onglet `Triggers` dans `WorkspaceDetailPanel`

Nouveau tab après `Playground`. Tableau des triggers actifs par workspace :

| Extension | Prompts | Activé | Actions |
|-----------|---------|--------|---------|

Bouton **+ Trigger** → `AddTriggerDialog.tsx` :
1. Extension (`.cs`, `.py`…)
2. Liste de prompts à exécuter (ordre drag-or-number) :
   - Select template (from `/api/admin/prompts`)
   - Select LLM (from `useLlmConfigs(workspace)`)
   - order_index auto-incrémenté

### i18n

Nouveaux namespaces `prompts` et `triggers` (fr + en).

### Sidebar

Ajouter une entrée **Prompts** dans la navigation principale (après `Models`).

---

## Tests backend

- `test_run_enrichments_calls_llm` — vérifie l'appel LLM + upsert `document_enrichments`
- `test_run_enrichments_skips_if_hash_unchanged` — déduplication
- `test_run_enrichments_cleans_on_empty_result` — résultat vide → suppression
- `test_run_enrichments_no_trigger` — extension sans trigger → rien à faire

---

## Périmètre hors-scope

- Réexécution manuelle des enrichissements (jalon futur)
- Visualisation des enrichissements dans le Playground (jalon futur)
- Triggers sur les fichiers supprimés (nettoyage partiel — les enrichissements existants sont supprimés lors du prochain run si le fichier disparaît du git diff)
