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

export type RerankSpec = {
  provider: string;
  model: string;
  api_key_ref: string | null;
  base_url: string | null;
  top_k_pre_rerank: number;
};

export type WorkspaceCreate = {
  name: string;
  indexer: {
    provider: string;
    model: string;
    api_key_ref: string | null;
    base_url: string | null;
  };
  rerank?: RerankSpec | undefined;
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
  name: string | null;
  type: "git";
  config: SourceConfig;
  last_indexed_at: string | null;
  created_at: string;
  branch_warning?: string | null;
};

type SourceConfigInput = {
  url: string;
  branch?: string;
  include: string[];
  exclude: string[];
};

export type SourceCreateRequest = {
  name: string;
  type: "git";
  git_provider?: string;
  auth_type: "token" | "ssh";
  auth_ref?: string;
  ssh_key_ref?: string;
  ssh_username?: string;
  config: SourceConfigInput;
};

export type SourceUpdateRequest = {
  git_provider?: string;
  auth_type?: "token" | "ssh";
  auth_ref?: string;
  ssh_key_ref?: string;
  ssh_username?: string;
  config: SourceConfigInput;
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

export type JobFileEntry = {
  path: string;
  change_type: "added" | "modified" | "deleted";
};

export type JobFilesResponse = {
  files: JobFileEntry[];
  total: number;
  limit: number;
};

export type ApiKeyRotateResponse = {
  api_key: string;
};

export type DetectBranchesResponse = {
  branches: string[];
  default: string | null;
};
