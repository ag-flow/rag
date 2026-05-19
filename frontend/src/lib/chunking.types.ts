// Miroir des schemas Pydantic backend (cf. backend/src/rag/schemas/admin.py).
// `ChunkingConfig` correspond à ChunkingConfigResponse.
// `ChunkingSpec` correspond à ChunkingConfigSpec (body PUT).

export type ChunkingStrategy = "paragraph";

export type ChunkingConfig = {
  workspace_id: string;
  strategy: ChunkingStrategy;
  max_chars: number;
  min_chars: number;
  overlap_chars: number;
  extras: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ChunkingSpec = {
  strategy: ChunkingStrategy;
  max_chars: number;
  min_chars: number;
  overlap_chars: number;
  extras: Record<string, unknown>;
};

export type ChunkingChangeRequiresReindexBody = {
  error: "chunking_change_requires_reindex";
  workspace: string;
  current: string;
  new: string;
  action: string;
};
