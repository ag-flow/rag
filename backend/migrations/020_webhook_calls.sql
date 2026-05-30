-- Migration 020 — webhook_calls (audit log, rétention 24h)

CREATE TABLE webhook_calls (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id   UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    webhook_id     UUID NOT NULL REFERENCES workspace_webhooks(id) ON DELETE CASCADE,
    job_id         UUID NOT NULL REFERENCES index_jobs(id),
    correlation_id TEXT NOT NULL,
    triggered_by   TEXT NOT NULL,
    webhook_url    TEXT NOT NULL,
    http_status    INT,
    error          TEXT,
    duration_ms    INT,
    called_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_webhook_calls_workspace ON webhook_calls(workspace_id, called_at DESC);
CREATE INDEX idx_webhook_calls_purge     ON webhook_calls(called_at);
