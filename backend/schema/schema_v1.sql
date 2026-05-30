-- Schema v1 — État consolidé de toutes les migrations (000-032)
-- Généré à partir des migrations 000 à 032.
-- Exécutable en one-shot sur une base vide.

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------------
-- Suivi des migrations
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Coffres Harpocrate
-- (créé avant workspaces car provider_api_keys/git_credentials/ssh_keys y référencent)
-- ---------------------------------------------------------------------------

CREATE TABLE harpocrate_vaults (
    id                uuid        PRIMARY KEY,
    name              text        NOT NULL UNIQUE,
    label             text        NOT NULL,
    base_url          text        NOT NULL,
    api_key_id        text        NOT NULL,
    api_key_encrypted bytea       NOT NULL,
    probe_path        text        NULL,
    is_default        boolean     NOT NULL DEFAULT false,
    owner_id          text        NOT NULL DEFAULT '',
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

-- Un seul coffre par défaut à la fois (index unique partiel)
CREATE UNIQUE INDEX harpocrate_vaults_one_default
    ON harpocrate_vaults (is_default)
    WHERE is_default;

CREATE INDEX harpocrate_vaults_name  ON harpocrate_vaults (name);
CREATE INDEX harpocrate_vaults_owner ON harpocrate_vaults (owner_id);

-- ---------------------------------------------------------------------------
-- Workspaces
-- (migrations 001, 010, 015 intégrées : api_key_hash → api_key_encrypted → api_key_ref)
-- ---------------------------------------------------------------------------

CREATE TABLE workspaces (
    id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name                  TEXT        NOT NULL UNIQUE,
    api_key_ref           TEXT        NOT NULL,
    api_key_fingerprint   TEXT        NOT NULL,
    rag_cnx               TEXT        NOT NULL,
    rag_base              TEXT        NOT NULL,
    sync_interval_seconds INT         NOT NULL DEFAULT 300,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_workspaces_name ON workspaces (name);
CREATE UNIQUE INDEX idx_workspaces_apikey_fingerprint ON workspaces (api_key_fingerprint);

-- ---------------------------------------------------------------------------
-- Sources de workspace
-- (migrations 002, 016 intégrées : ajout colonne name)
-- ---------------------------------------------------------------------------

CREATE TABLE workspace_sources (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID        NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    type            TEXT        NOT NULL DEFAULT 'git',
    name            TEXT,
    config          JSONB       NOT NULL,
    last_indexed_at TIMESTAMPTZ,
    next_sync_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_workspace_sources_workspace ON workspace_sources (workspace_id);
CREATE INDEX idx_sources_next_sync ON workspace_sources (next_sync_at)
    WHERE next_sync_at IS NOT NULL;
CREATE UNIQUE INDEX uq_workspace_sources_name
    ON workspace_sources (workspace_id, name)
    WHERE name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Jobs d'indexation
-- (migrations 003, 007, 013, 018 intégrées :
--   triggered_by élargi à 5 valeurs, status élargi avec 'skipped', correlation_id)
-- ---------------------------------------------------------------------------

CREATE TABLE index_jobs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID        NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_id       UUID        REFERENCES workspace_sources(id) ON DELETE SET NULL,
    triggered_by    TEXT        NOT NULL
                                CHECK (triggered_by IN (
                                    'webhook',
                                    'manual',
                                    'push',
                                    'schedule',
                                    'reindex_indexer_change',
                                    'reindex_chunking_change'
                                )),
    status          TEXT        NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending', 'running', 'done', 'error', 'skipped')),
    correlation_id  TEXT,
    files_changed   INT         NOT NULL DEFAULT 0,
    files_skipped   INT         NOT NULL DEFAULT 0,
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    duration_ms     INT
);

CREATE INDEX idx_jobs_status_workspace   ON index_jobs (status, workspace_id);
CREATE INDEX idx_jobs_workspace_finished ON index_jobs (workspace_id, finished_at DESC NULLS LAST);
CREATE INDEX idx_jobs_workspace_started  ON index_jobs (workspace_id, started_at  DESC NULLS LAST);

-- ---------------------------------------------------------------------------
-- Documents indexés
-- ---------------------------------------------------------------------------

CREATE TABLE indexed_documents (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID        NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    path         TEXT        NOT NULL,
    content_hash TEXT        NOT NULL,
    indexer_used TEXT        NOT NULL,
    indexed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, path)
);

CREATE INDEX idx_docs_workspace ON indexed_documents (workspace_id);

-- ---------------------------------------------------------------------------
-- Configuration OIDC
-- ---------------------------------------------------------------------------

CREATE TABLE oidc_config (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    issuer            TEXT        NOT NULL,
    client_id         TEXT        NOT NULL,
    client_secret_ref TEXT        NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Dimensions des modèles d'embedding
-- (migrations 005, 008, 021, 022, 023, 026)
-- ---------------------------------------------------------------------------

CREATE TABLE model_dimensions (
    provider   TEXT        NOT NULL,
    model      TEXT        NOT NULL,
    dimension  INT         NOT NULL CHECK (dimension > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, model)
);

INSERT INTO model_dimensions (provider, model, dimension) VALUES
    -- OpenAI
    ('openai',       'text-embedding-3-small',    1536),
    ('openai',       'text-embedding-3-large',    3072),
    -- Voyage AI
    ('voyage',       'voyage-3',                  1024),
    ('voyage',       'voyage-code-3',             1024),
    ('voyage',       'voyage-3-lite',              512),
    ('voyage',       'voyage-multilingual-2',     1024),
    -- Ollama
    ('ollama',       'qwen2.5-coder:14b',         4096),
    ('ollama',       'nomic-embed-text',            768),
    ('ollama',       'mxbai-embed-large',          1024),
    ('ollama',       'bge-m3',                    1024),
    ('ollama',       'nomic-embed-text:v1.5',      768),
    ('ollama',       'qwen3-embedding-0.6b',      1024),
    ('ollama',       'qwen3-embedding-8b',        4096),
    -- Mistral AI
    ('mistral',      'mistral-embed',             1024),
    ('mistral',      'codestral-embed-2505',      3072),
    -- Jina AI
    ('jina',         'jina-embeddings-v3',        1024),
    -- Azure OpenAI
    ('azure-openai', 'text-embedding-3-small',    1536),
    ('azure-openai', 'text-embedding-3-large',    3072),
    ('azure-openai', 'text-embedding-ada-002',    1536)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Configuration des indexeurs
-- ---------------------------------------------------------------------------

CREATE TABLE indexer_configs (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID        NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    provider     TEXT        NOT NULL,
    model        TEXT        NOT NULL,
    base_url     TEXT,
    api_key_ref  TEXT,
    dimension    INT         NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id)
);

CREATE INDEX idx_indexer_configs_workspace ON indexer_configs (workspace_id);

-- ---------------------------------------------------------------------------
-- Configuration du reranking par workspace
-- ---------------------------------------------------------------------------

CREATE TABLE rerank_configs (
    workspace_id      UUID        PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    provider          TEXT        NOT NULL,
    model             TEXT        NOT NULL,
    base_url          TEXT,
    api_key_ref       TEXT,
    top_k_pre_rerank  INT         NOT NULL DEFAULT 50 CHECK (top_k_pre_rerank > 0),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Configuration du chunking par workspace
-- (migrations 012, 014 intégrées : stratégies 'paragraph' et 'markdown')
-- ---------------------------------------------------------------------------

CREATE TABLE chunking_configs (
    workspace_id  UUID        PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    strategy      TEXT        NOT NULL CHECK (strategy IN ('paragraph', 'markdown')),
    max_chars     INT         NOT NULL CHECK (max_chars  > 0),
    min_chars     INT         NOT NULL CHECK (min_chars  >= 0 AND min_chars < max_chars),
    overlap_chars INT         NOT NULL CHECK (overlap_chars >= 0 AND overlap_chars < max_chars),
    extras        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Peuplement des workspaces existants avec la stratégie par défaut
INSERT INTO chunking_configs (workspace_id, strategy, max_chars, min_chars, overlap_chars)
SELECT id, 'paragraph', 2000, 200, 200
FROM workspaces
ON CONFLICT (workspace_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Fichiers traités par job
-- ---------------------------------------------------------------------------

CREATE TABLE index_job_files (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id      UUID NOT NULL REFERENCES index_jobs(id) ON DELETE CASCADE,
    path        TEXT NOT NULL,
    change_type TEXT NOT NULL CHECK (change_type IN ('added', 'modified', 'deleted'))
);

CREATE INDEX idx_job_files_job ON index_job_files (job_id);

-- ---------------------------------------------------------------------------
-- Payloads des push jobs
-- ---------------------------------------------------------------------------

CREATE TABLE push_job_payloads (
    job_id  UUID PRIMARY KEY REFERENCES index_jobs(id) ON DELETE CASCADE,
    path    TEXT NOT NULL,
    content TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- Webhooks de workspace
-- ---------------------------------------------------------------------------

CREATE TABLE workspace_webhooks (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID        NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name         TEXT        NOT NULL,
    url          TEXT        NOT NULL,
    enabled      BOOLEAN     DEFAULT true,
    created_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (workspace_id, name)
);

CREATE TABLE webhook_headers (
    id         UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_id UUID    NOT NULL REFERENCES workspace_webhooks(id) ON DELETE CASCADE,
    name       TEXT    NOT NULL,
    value      TEXT,
    vault_ref  TEXT,
    enabled    BOOLEAN DEFAULT true
);

-- ---------------------------------------------------------------------------
-- Journal des appels webhooks (rétention 24h)
-- ---------------------------------------------------------------------------

CREATE TABLE webhook_calls (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id   UUID        NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    webhook_id     UUID        NOT NULL REFERENCES workspace_webhooks(id) ON DELETE CASCADE,
    job_id         UUID        NOT NULL REFERENCES index_jobs(id),
    correlation_id TEXT        NOT NULL,
    triggered_by   TEXT        NOT NULL,
    webhook_url    TEXT        NOT NULL,
    http_status    INT,
    error          TEXT,
    duration_ms    INT,
    called_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_webhook_calls_workspace ON webhook_calls (workspace_id, called_at DESC);
CREATE INDEX idx_webhook_calls_purge     ON webhook_calls (called_at);

-- ---------------------------------------------------------------------------
-- Clés API provider (dans coffres Harpocrate)
-- (migrations 024, 027 intégrées : ajout expires_at)
-- ---------------------------------------------------------------------------

CREATE TABLE provider_api_keys (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    key_id     TEXT        NOT NULL,
    label      TEXT        NOT NULL,
    provider   TEXT        NOT NULL,
    vault_id   UUID        NOT NULL REFERENCES harpocrate_vaults(id) ON DELETE RESTRICT,
    harpo_path TEXT        NOT NULL,
    expires_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (vault_id, provider, key_id)
);

-- ---------------------------------------------------------------------------
-- Tokens Git (dans coffres Harpocrate)
-- (migrations 025, 027 intégrées : ajout expires_at)
-- ---------------------------------------------------------------------------

CREATE TABLE git_credentials (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    key_id     TEXT        NOT NULL,
    label      TEXT        NOT NULL,
    host       TEXT        NOT NULL,
    scope_url  TEXT        NULL,
    vault_id   UUID        NOT NULL REFERENCES harpocrate_vaults(id) ON DELETE RESTRICT,
    harpo_path TEXT        NOT NULL,
    expires_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (vault_id, host, key_id)
);

-- ---------------------------------------------------------------------------
-- Clés SSH (dans coffres Harpocrate)
-- ---------------------------------------------------------------------------

CREATE TABLE ssh_keys (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    key_id               TEXT        NOT NULL,
    name                 TEXT        NOT NULL,
    key_type             TEXT        NOT NULL,
    public_key           TEXT        NOT NULL,
    passphrase_protected BOOLEAN     NOT NULL DEFAULT false,
    vault_id             UUID        NOT NULL REFERENCES harpocrate_vaults(id) ON DELETE RESTRICT,
    harpo_path           TEXT        NOT NULL,
    created_at           TIMESTAMPTZ DEFAULT now(),
    UNIQUE (vault_id, key_id)
);

-- ---------------------------------------------------------------------------
-- Configurations LLM par workspace (RAG Playground)
-- ---------------------------------------------------------------------------

CREATE TABLE workspace_llm_configs (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID        NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    provider     TEXT        NOT NULL,
    model        TEXT        NOT NULL,
    base_url     TEXT,
    api_key_ref  TEXT,
    enabled      BOOLEAN     NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (workspace_id, provider, model)
);

CREATE INDEX workspace_llm_configs_ws ON workspace_llm_configs (workspace_id);

-- ---------------------------------------------------------------------------
-- Templates de prompts (bibliothèque globale)
-- ---------------------------------------------------------------------------

CREATE TABLE prompt_templates (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT        NOT NULL UNIQUE,
    language      TEXT        NOT NULL,
    description   TEXT,
    metadata_key  TEXT        NOT NULL,
    result_type   TEXT        NOT NULL DEFAULT 'text',
    result_schema JSONB,
    prompt        TEXT        NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX prompt_templates_language ON prompt_templates (language);

-- ---------------------------------------------------------------------------
-- Déclencheurs par extension de fichier
-- ---------------------------------------------------------------------------

CREATE TABLE workspace_extension_triggers (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID        NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    extension    TEXT        NOT NULL,
    enabled      BOOLEAN     NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (workspace_id, extension)
);

CREATE INDEX workspace_extension_triggers_ws ON workspace_extension_triggers (workspace_id);

-- ---------------------------------------------------------------------------
-- Prompts associés à un déclencheur (ordre séquentiel)
-- ---------------------------------------------------------------------------

CREATE TABLE workspace_extension_trigger_prompts (
    id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_id  UUID    NOT NULL REFERENCES workspace_extension_triggers(id) ON DELETE CASCADE,
    template_id UUID    NOT NULL REFERENCES prompt_templates(id),
    llm_id      UUID    NOT NULL REFERENCES workspace_llm_configs(id),
    order_index INT     NOT NULL,
    enabled     BOOLEAN NOT NULL DEFAULT true,
    UNIQUE (trigger_id, order_index)
);

-- ---------------------------------------------------------------------------
-- Résultats d'enrichissement LLM (déduplication par hash)
-- ---------------------------------------------------------------------------

CREATE TABLE document_enrichments (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID        NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    path         TEXT        NOT NULL,
    template_id  UUID        NOT NULL REFERENCES prompt_templates(id),
    metadata_key TEXT        NOT NULL,
    result_type  TEXT        NOT NULL,
    result       TEXT        NOT NULL,
    result_hash  TEXT        NOT NULL,
    llm_provider TEXT        NOT NULL,
    llm_model    TEXT        NOT NULL,
    indexed_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (workspace_id, path, template_id)
);

CREATE INDEX document_enrichments_ws_path ON document_enrichments (workspace_id, path);

-- ---------------------------------------------------------------------------
-- Référentiel des langues / cultures (BCP 47)
-- ---------------------------------------------------------------------------

CREATE TABLE languages (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    code       TEXT        NOT NULL UNIQUE,
    label      TEXT        NOT NULL,
    built_in   BOOLEAN     NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO languages (code, label, built_in) VALUES
    ('fr-FR', 'Français (France)',                              true),
    ('fr-BE', 'Français (Belgique)',                            true),
    ('fr-CH', 'Français (Suisse)',                              true),
    ('en-US', 'English (United States)',                        true),
    ('en-GB', 'English (United Kingdom)',                       true),
    ('en-AU', 'English (Australia)',                            true),
    ('de-DE', 'Deutsch (Deutschland)',                          true),
    ('de-AT', 'Deutsch (Österreich)',                           true),
    ('de-CH', 'Deutsch (Schweiz)',                              true),
    ('es-ES', 'Español (España)',                               true),
    ('es-MX', 'Español (México)',                               true),
    ('pt-BR', 'Português (Brasil)',                             true),
    ('pt-PT', 'Português (Portugal)',                           true),
    ('it-IT', 'Italiano (Italia)',                              true),
    ('nl-NL', 'Nederlands (Nederland)',                         true),
    ('pl-PL', 'Polski (Polska)',                                true),
    ('cs-CZ', 'Čeština (Česká republika)',                      true),
    ('hu-HU', 'Magyar (Magyarország)',                          true),
    ('ro-RO', 'Română (România)',                               true),
    ('zh-CN', '中文 (简体)',                                     true),
    ('zh-TW', '中文 (繁體)',                                     true),
    ('ja-JP', '日本語 (日本)',                                   true),
    ('ko-KR', '한국어 (대한민국)',                                true),
    ('ar-SA', 'العربية (المملكة العربية السعودية)',              true)
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Marquer toutes les migrations comme appliquées
-- (permet au runner de migrations de démarrer sans réappliquer quoi que ce soit)
-- ---------------------------------------------------------------------------

INSERT INTO schema_migrations (version) VALUES
    ('000_schema_migrations'),
    ('001_init'),
    ('002_workspace_sources'),
    ('003_jobs'),
    ('004_oidc'),
    ('005_model_dimensions'),
    ('006_index_jobs_idx'),
    ('007_index_jobs_reindex_trigger'),
    ('008_ollama_mxbai_embed_large'),
    ('009_harpocrate_vaults'),
    ('010_workspace_apikey_encrypted'),
    ('011_rerank_configs'),
    ('012_chunking_configs'),
    ('013_index_jobs_chunking_change_trigger'),
    ('014_chunking_strategy_markdown'),
    ('015_workspaces_apikey_ref'),
    ('016_workspace_sources_name'),
    ('017_index_job_files'),
    ('018_push_job_payloads'),
    ('019_webhooks'),
    ('020_webhook_calls'),
    ('021_embedding_models_2026'),
    ('022_embedding_models_ollama_qwen'),
    ('023_embedding_models_mistral_jina'),
    ('024_provider_api_keys'),
    ('025_git_credentials'),
    ('026_azure_openai_models'),
    ('027_add_expires_at'),
    ('028_ssh_keys'),
    ('029_vault_owner'),
    ('030_workspace_llm_configs'),
    ('031_enrichment_triggers'),
    ('032_languages')
ON CONFLICT (version) DO NOTHING;
