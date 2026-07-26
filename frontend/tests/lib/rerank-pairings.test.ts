import { describe, it, expect } from "vitest";
import { likeMatch, pairingNote } from "@/lib/models";
import type { RerankPairing } from "@/lib/models.types";

const PAIRINGS: RerankPairing[] = [
  {
    embed_provider_like: "cohere",
    embed_model_like: "embed-%",
    rerank_provider_like: "cohere",
    rerank_model_like: "rerank-%",
    note: "Pipeline intégré Cohere",
  },
  {
    embed_provider_like: "%",
    embed_model_like: "%qwen3-embedding%",
    rerank_provider_like: "%",
    rerank_model_like: "%qwen3-reranker%",
    note: "Même famille Qwen3",
  },
  {
    embed_provider_like: "%",
    embed_model_like: "%bge-m3",
    rerank_provider_like: "deepinfra",
    rerank_model_like: "Qwen/Qwen3-Reranker-4B",
    note: "Qwen3-4B améliore toutes les configs",
  },
];

describe("likeMatch", () => {
  it("joker % et insensibilité à la casse", () => {
    expect(likeMatch("%qwen3-reranker%", "Qwen/Qwen3-Reranker-8B")).toBe(true);
    expect(likeMatch("embed-%", "embed-v4")).toBe(true);
    expect(likeMatch("embed-%", "text-embed-v4")).toBe(false);
    expect(likeMatch("cohere", "COHERE")).toBe(true);
  });

  it("échappe les métacaractères regex du motif", () => {
    expect(likeMatch("Qwen/Qwen3-Reranker-4B", "Qwen/Qwen3-Reranker-4B")).toBe(true);
    expect(likeMatch("a.b", "axb")).toBe(false);
  });
});

describe("pairingNote", () => {
  it("même famille : ollama qwen3-embedding → deepinfra Qwen3-Reranker", () => {
    const note = pairingNote(
      PAIRINGS,
      { provider: "ollama", model: "qwen3-embedding:8b" },
      { provider: "deepinfra", model: "Qwen/Qwen3-Reranker-8B" },
    );
    expect(note).toBe("Même famille Qwen3");
  });

  it("cross-provider : bge-m3 → Qwen3-Reranker-4B deepinfra uniquement", () => {
    const embed = { provider: "ollama", model: "bge-m3" };
    expect(pairingNote(PAIRINGS, embed, { provider: "deepinfra", model: "Qwen/Qwen3-Reranker-4B" }))
      .toBe("Qwen3-4B améliore toutes les configs");
    expect(pairingNote(PAIRINGS, embed, { provider: "ollama", model: "ms-marco-minilm" })).toBeNull();
  });

  it("pas de préco quand l'embedder ne matche pas", () => {
    expect(
      pairingNote(
        PAIRINGS,
        { provider: "openai", model: "text-embedding-3-small" },
        { provider: "cohere", model: "rerank-v3.5" },
      ),
    ).toBeNull();
  });
});
