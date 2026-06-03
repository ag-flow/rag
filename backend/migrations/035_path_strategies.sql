-- Migration 035 — table path_strategies (stratégie de vectorisation par path)
CREATE TABLE path_strategies (
    workspace_id  UUID        NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    path          TEXT        NOT NULL,
    strategy      TEXT        NOT NULL DEFAULT 'replace'
                              CHECK (strategy IN ('replace', 'append')),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by    TEXT        NOT NULL DEFAULT 'ui'
                              CHECK (updated_by IN ('ui', 'strategy_file')),
    PRIMARY KEY (workspace_id, path)
);
