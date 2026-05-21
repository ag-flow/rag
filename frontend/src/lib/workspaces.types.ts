// 8 types TS miroirs des schemas Pydantic backend
// (cf. backend/src/rag/schemas/admin.py)

export type IndexerSpec = {
  provider: string;
  model: string;
  api_key_ref: string | null;
  base_url: string | null;
};

export type Workspace = {
  id: string;
  name: string;
  indexer: IndexerSpec;
  sources_count: number;
  documents_count: number;
  last_indexed_at: string | null;
  created_at: string;
};

export type WorkspaceCreate = {
  name: string;
  api_key_vault: string;
  indexer: {
    provider: string;
    model: string;
    api_key: string | null;
    base_url?: string | null;
  };
};

export type WorkspaceCreateResponse = {
  id: string;
  name: string;
  api_key: string;
  created_at: string;
};

export type WorkspacePatchRequest = {
  indexer: { api_key_ref: string };
};

export type SourceConfig = {
  url: string;
  branch: string;
  auth_ref: string | null;
  include: string[];
  exclude: string[];
};

export type Source = {
  id: string;
  type: "git";
  config: SourceConfig;
  last_indexed_at: string | null;
  created_at: string;
};

export type SourceCreateRequest = {
  type: "git";
  config: SourceConfig;
};

export type Job = {
  id: string;
  triggered_by:
    | "webhook"
    | "manual"
    | "push"
    | "schedule"
    | "reindex_indexer_change"
    | "reindex_chunking_change";
  status: "pending" | "running" | "done" | "error";
  files_changed: number;
  files_skipped: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
};

export type ApiKeyRotateResponse = {
  api_key: string;
};
