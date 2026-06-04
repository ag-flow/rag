-- Migration 037 — colonne service dans model_dimensions
-- Identifie la capacité IA (service) indépendamment de la plateforme d'accès (provider).

ALTER TABLE model_dimensions ADD COLUMN service TEXT NOT NULL DEFAULT '';

UPDATE model_dimensions SET service = provider
    WHERE provider IN ('openai', 'voyage', 'mistral', 'jina', 'gemini', 'ollama', 'dashscope');

UPDATE model_dimensions SET service = 'openai'
    WHERE provider = 'azure-openai';
