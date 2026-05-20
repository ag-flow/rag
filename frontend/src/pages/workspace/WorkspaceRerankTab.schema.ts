import { z } from "zod";
import type { RerankProvider } from "@/lib/rerank.types";

export const RERANK_PROVIDERS: RerankProvider[] = ["cohere", "voyage", "ollama"];

export const rerankFormSchema = z
  .object({
    provider: z.enum(["cohere", "voyage", "ollama"]),
    model: z.string().min(1, "required"),
    api_key_ref: z
      .string()
      .regex(/^[a-zA-Z0-9_]+$/, "alphanum_underscore_only")
      .nullable(),
    base_url: z.string().url("invalid_url").nullable(),
    top_k_pre_rerank: z.coerce.number().int().min(1, "min").max(500, "max"),
  })
  .superRefine((data, ctx) => {
    if ((data.provider === "cohere" || data.provider === "voyage") && !data.api_key_ref) {
      ctx.addIssue({
        path: ["api_key_ref"],
        code: z.ZodIssueCode.custom,
        message: "required_for_provider",
      });
    }
    if (data.provider === "ollama" && !data.base_url) {
      ctx.addIssue({
        path: ["base_url"],
        code: z.ZodIssueCode.custom,
        message: "required_for_provider",
      });
    }
  });

export type RerankFormValues = z.infer<typeof rerankFormSchema>;

export const EMPTY_RERANK_FORM: RerankFormValues = {
  provider: "cohere",
  model: "",
  api_key_ref: null,
  base_url: null,
  top_k_pre_rerank: 50,
};
