import { z } from "zod";

const indexerSchema = z.object({
  provider: z.string().min(1),
  model: z.string().min(1),
  api_key_ref: z.string().nullable().optional(),
  base_url: z.string().nullable().optional(),
});

const rerankSchema = z.object({
  provider: z.string().min(1),
  model: z.string().min(1),
  api_key_ref: z.string().nullable().optional(),
  base_url: z.string().nullable().optional(),
  top_k_pre_rerank: z.number().int().min(1).max(500).default(50),
});

export const workspaceCreateSchema = z.object({
  name: z.string().regex(/^[a-z][a-z0-9_-]{0,62}$/),
  indexer: indexerSchema,
  rerank: rerankSchema.nullable().optional(),
});

export interface MeResponse {
  sub: string;
  email: string | null;
  name: string | null;
  roles: string[];
}

export const vaultUpdateSchema = z.object({
  label: z.string().min(1, "Libellé requis").max(128),
  base_url: z
    .string()
    .min(8)
    .max(512)
    .regex(/^https?:\/\//, "Doit commencer par http:// ou https://"),
  probe_path: z
    .string()
    .max(512)
    .regex(/^[a-zA-Z0-9_/-]*$/, "Caractères autorisés : a-zA-Z0-9_/-")
    .optional()
    .default(""),
});

export type VaultUpdateForm = z.infer<typeof vaultUpdateSchema>;

export const vaultCreateSchema = z.object({
  name: z
    .string()
    .min(3)
    .max(64)
    .regex(/^[a-z][a-z0-9_-]{2,63}$/, "Format : ^[a-z][a-z0-9_-]{2,63}$"),
  label: z.string().min(1, "Libellé requis").max(128),
  base_url: z
    .string()
    .min(8)
    .max(512)
    .regex(/^https?:\/\//, "Doit commencer par http:// ou https://"),
  api_key_id: z.string().min(1).max(128),
  api_key: z.string().min(8, "Min 8 caractères").max(2048),
  probe_path: z
    .string()
    .max(512)
    .regex(/^[a-zA-Z0-9_/-]*$/, "Caractères autorisés : a-zA-Z0-9_/-")
    .optional()
    .default(""),
  is_default: z.boolean().default(true),
});

export type VaultCreateForm = z.infer<typeof vaultCreateSchema>;
