-- Migration 034 — webhook_enabled sur workspace_sources
ALTER TABLE workspace_sources
  ADD COLUMN webhook_enabled BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX idx_sources_webhook_enabled
  ON workspace_sources(webhook_enabled)
  WHERE webhook_enabled = true;
