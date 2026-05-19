import { z } from "zod";
import type { ChunkingStrategy } from "@/lib/chunking.types";

export const CHUNKING_STRATEGIES: ChunkingStrategy[] = ["paragraph"];

export const chunkingFormSchema = z
  .object({
    strategy: z.enum(["paragraph"]),
    max_chars: z.coerce.number().int().min(1, "min"),
    min_chars: z.coerce.number().int().min(0, "min"),
    overlap_chars: z.coerce.number().int().min(0, "min"),
  })
  .superRefine((data, ctx) => {
    if (data.min_chars >= data.max_chars) {
      ctx.addIssue({
        path: ["min_chars"],
        code: z.ZodIssueCode.custom,
        message: "min_lt_max",
      });
    }
    if (data.overlap_chars >= data.max_chars) {
      ctx.addIssue({
        path: ["overlap_chars"],
        code: z.ZodIssueCode.custom,
        message: "overlap_lt_max",
      });
    }
  });

export type ChunkingFormValues = z.infer<typeof chunkingFormSchema>;

export const DEFAULT_CHUNKING_FORM: ChunkingFormValues = {
  strategy: "paragraph",
  max_chars: 2000,
  min_chars: 200,
  overlap_chars: 200,
};
