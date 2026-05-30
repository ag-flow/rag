-- Migration 031 — déclencheurs par extension + enrichissement LLM (spec 13)

-- Bibliothèque globale de prompts
CREATE TABLE prompt_templates (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL UNIQUE,
    language      TEXT NOT NULL,           -- langage de programmation : "csharp", "python", etc.
    description   TEXT,
    metadata_key  TEXT NOT NULL,           -- clé du résultat : "documentation", "public_functions"
    result_type   TEXT NOT NULL DEFAULT 'text',  -- "text" | "json"
    result_schema JSONB,                   -- JSON Schema si result_type = "json"
    prompt        TEXT NOT NULL,           -- template avec placeholder {content}
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX prompt_templates_language ON prompt_templates (language);

-- Triggers par extension de fichier sur un workspace
CREATE TABLE workspace_extension_triggers (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    extension    TEXT NOT NULL,            -- ex: ".cs", ".py", ".ts" (avec point)
    enabled      BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (workspace_id, extension)
);

CREATE INDEX workspace_extension_triggers_ws ON workspace_extension_triggers (workspace_id);

-- Prompts associés à un trigger (ordre d'exécution séquentiel)
CREATE TABLE workspace_extension_trigger_prompts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_id  UUID NOT NULL REFERENCES workspace_extension_triggers(id) ON DELETE CASCADE,
    template_id UUID NOT NULL REFERENCES prompt_templates(id),
    llm_id      UUID NOT NULL REFERENCES workspace_llm_configs(id),
    order_index INT NOT NULL,              -- commence à 1
    enabled     BOOLEAN NOT NULL DEFAULT true,
    UNIQUE (trigger_id, order_index)
);

-- Résultats d'enrichissement stockés + hashés pour déduplication
CREATE TABLE document_enrichments (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    path         TEXT NOT NULL,            -- path du document source
    template_id  UUID NOT NULL REFERENCES prompt_templates(id),
    metadata_key TEXT NOT NULL,            -- snapshot de la clé au moment de l'exécution
    result_type  TEXT NOT NULL,            -- "text" | "json"
    result       TEXT NOT NULL,            -- résultat du prompt LLM
    result_hash  TEXT NOT NULL,            -- SHA-256(result) pour déduplication
    llm_provider TEXT NOT NULL,            -- snapshot provider
    llm_model    TEXT NOT NULL,            -- snapshot modèle
    indexed_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (workspace_id, path, template_id)
);

CREATE INDEX document_enrichments_ws_path ON document_enrichments (workspace_id, path);
