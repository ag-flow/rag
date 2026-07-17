-- Migration 061 — contextual retrieval « Prompt B » (enabler epic retrieval)
--
-- Étend le système d'enrichissement EXISTANT (pas de second système de
-- prompts) avec deux axes :
--   - target : 'document' | 'chunk' | 'region:<type>[:<qualifier>]'
--   - timing : 'post_index_metadata' (existant — métadonnée séparée)
--            | 'embedding_inline'   (nouveau — injecté dans le texte embeddé)
-- L'enrichissement actuel devient le cas (document, post_index_metadata).
-- Combinaisons supportées uniquement : document+post_index_metadata,
-- chunk+embedding_inline, region:*+embedding_inline.
--
-- `prompt_version` sert de clé d'invalidation du cache de contexte : bumpé
-- automatiquement quand le texte du prompt change (patch_prompt_template).

ALTER TABLE prompt_templates
    ADD COLUMN target TEXT NOT NULL DEFAULT 'document',
    ADD COLUMN timing TEXT NOT NULL DEFAULT 'post_index_metadata',
    ADD COLUMN prompt_version INT NOT NULL DEFAULT 1;

ALTER TABLE prompt_templates
    ADD CONSTRAINT prompt_templates_timing_check
        CHECK (timing IN ('post_index_metadata', 'embedding_inline')),
    ADD CONSTRAINT prompt_templates_target_timing_check CHECK (
        (timing = 'post_index_metadata' AND target = 'document')
        OR (timing = 'embedding_inline' AND (target = 'chunk' OR target LIKE 'region:%'))
    );

-- Cache du contexte généré (idempotence du diff ensembliste, spec « Prompt B ») :
-- le contexte entre dans le texte embeddé donc dans chunk_hash — un LLM non
-- déterministe casserait le diff. Clé = hash du texte SOURCE (avant injection)
-- + template + prompt_version : on ne régénère que si la source ou le prompt
-- change. Pas de TTL : purge par CASCADE workspace/template.
CREATE TABLE chunk_context_cache (
    workspace_id   UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_hash    TEXT NOT NULL,
    template_id    UUID NOT NULL REFERENCES prompt_templates(id) ON DELETE CASCADE,
    prompt_version INT  NOT NULL,
    context        TEXT NOT NULL,
    llm_provider   TEXT NOT NULL,
    llm_model      TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, source_hash, template_id, prompt_version)
);
