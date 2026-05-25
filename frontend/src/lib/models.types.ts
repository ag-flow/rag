// Types miroirs du schema Pydantic ModelEntry
// (cf. backend/src/rag/schemas/admin.py:123)

export type ModelEntry = {
  provider: string;
  model: string;
  dimension: number;
  created_at: string;
};

export type ModelCreateRequest = {
  provider: string;
  model: string;
  dimension: number;
};
