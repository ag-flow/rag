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
  .refine((data) => data.indexer.provider === "ollama" || !!data.indexer.api_key_ref, {
    message: "api_key_ref_required",
    path: ["indexer", "api_key_ref"],
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
