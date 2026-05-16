import { z } from "zod";

export const workspaceCreateSchema = z
  .object({
    name: z
      .string()
      .min(1, "name_required")
      .max(64, "name_too_long")
      .regex(/^[a-z][a-z0-9_-]{0,62}$/, "name_invalid_format"),
    indexer: z.object({
      provider: z.enum(["openai", "voyage", "ollama"]),
      model: z.string().min(1, "model_required"),
      api_key_ref: z.string().min(1).optional(),
      base_url: z.string().url().optional(),
    }),
  })
  .refine(
    (data) => data.indexer.provider === "ollama" || !!data.indexer.api_key_ref,
    {
      message: "api_key_ref_required",
      path: ["indexer", "api_key_ref"],
    },
  );

export type WorkspaceCreate = z.infer<typeof workspaceCreateSchema>;

export interface Workspace {
  id: string;
  name: string;
  indexer: {
    provider: string;
    model: string;
    api_key_ref?: string;
    base_url?: string;
  };
  sources_count: number;
  documents_count: number;
  last_indexed_at: string | null;
  created_at: string;
}

export interface WorkspaceCreateResponse {
  name: string;
  api_key: string;
}

export interface ApiKeyRotateResponse {
  api_key: string;
}

export interface MeResponse {
  sub: string;
  email: string | null;
  name: string | null;
  roles: string[];
}
