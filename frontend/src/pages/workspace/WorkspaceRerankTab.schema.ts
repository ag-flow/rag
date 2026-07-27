import { z } from "zod";
import type { RerankProvider } from "@/lib/rerank.types";

export const RERANK_PROVIDERS: RerankProvider[] = [
  "cohere",
  "voyage",
  "jina",
  "dashscope",
  "azure-foundry",
  "ollama",
  "fireworks",
  "deepinfra",
  "mixedbread",
];

// Providers nécessitant une clé API (tous sauf ollama, qui tourne en local).
export const KEY_REQUIRED_PROVIDERS: RerankProvider[] = [
  "cohere",
  "voyage",
  "jina",
  "dashscope",
  "azure-foundry",
  "fireworks",
  "deepinfra",
  "mixedbread",
];

// Providers nécessitant un base_url : ollama (hôte du serveur local) et
// azure-foundry (URL complète de l'endpoint rerank du déploiement Azure).
export const BASE_URL_REQUIRED_PROVIDERS: RerankProvider[] = ["ollama", "azure-foundry"];

export const MODELS_BY_PROVIDER: Record<RerankProvider, string[]> = {
  cohere: [
    "rerank-v3.5",
    "rerank-english-v3.0",
    "rerank-multilingual-v3.0",
    "rerank-english-light-v3.0",
    "rerank-multilingual-light-v3.0",
  ],
  voyage: ["voyage-rerank-2", "voyage-rerank-2-lite", "voyage-rerank-1"],
  jina: ["jina-reranker-v2-base-multilingual", "jina-reranker-v1-base-en", "jina-colbert-v2"],
  dashscope: ["gte-rerank-v2", "gte-rerank"],
  // Cohere Rerank déployé sur Azure AI Foundry (mêmes IDs modèle que Cohere).
  "azure-foundry": ["rerank-v3.5", "rerank-multilingual-v3.0", "rerank-english-v3.0"],
  ollama: ["bge-reranker-v2-m3", "bge-reranker-base", "ms-marco-minilm"],
  fireworks: ["accounts/fireworks/models/qwen3-reranker-8b"],
  deepinfra: [
    "Qwen/Qwen3-Reranker-8B",
    "Qwen/Qwen3-Reranker-4B",
    "nvidia/llama-nemotron-rerank-vl-1b-v2",
  ],
  mixedbread: ["mxbai-rerank-large-v2", "mxbai-rerank-base-v2"],
};

export const rerankFormSchema = z
  .object({
    provider: z.enum([
      "cohere",
      "voyage",
      "jina",
      "dashscope",
      "azure-foundry",
      "ollama",
      "fireworks",
      "deepinfra",
      "mixedbread",
    ]),
    model: z.string().min(1, "required"),
    api_key_ref: z
      .string()
      .regex(/^[a-zA-Z0-9_]+$/, "alphanum_underscore_only")
      .nullable(),
    base_url: z.string().url("invalid_url").nullable(),
    top_k_pre_rerank: z.coerce.number().int().min(1, "min").max(500, "max"),
  })
  .superRefine((data, ctx) => {
    if (KEY_REQUIRED_PROVIDERS.includes(data.provider) && !data.api_key_ref) {
      ctx.addIssue({
        path: ["api_key_ref"],
        code: z.ZodIssueCode.custom,
        message: "required_for_provider",
      });
    }
    if (BASE_URL_REQUIRED_PROVIDERS.includes(data.provider) && !data.base_url) {
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
