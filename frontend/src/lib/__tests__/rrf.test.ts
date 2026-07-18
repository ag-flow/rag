import { describe, it, expect } from "vitest";
import { simulateRrf } from "@/lib/rrf";
import type { ChannelHit } from "@/lib/search-config.types";

const hit = (path: string, chunkIndex: number, rank: number): ChannelHit => ({
  path,
  chunk_index: chunkIndex,
  rank,
  score: 0.9,
});

describe("simulateRrf", () => {
  it("fusionne les contributions des deux canaux pour un même document", () => {
    const result = simulateRrf([hit("a.md", 0, 1)], [hit("a.md", 0, 2)], 60, 0.5, 0.5);
    expect(result).toHaveLength(1);
    expect(result[0]?.score).toBeCloseTo(0.5 / 61 + 0.5 / 62, 10);
  });

  it("un document absent d'un canal ne contribue rien sur ce canal", () => {
    const result = simulateRrf([hit("a.md", 0, 1)], [], 60, 0.5, 0.5);
    expect(result[0]?.score).toBeCloseTo(0.5 / 61, 10);
  });

  it("l'identité d'un document est path + chunk_index", () => {
    const result = simulateRrf([hit("a.md", 0, 1)], [hit("a.md", 1, 1)], 60, 0.5, 0.5);
    expect(result).toHaveLength(2);
  });

  it("trie par score décroissant", () => {
    const result = simulateRrf(
      [hit("a.md", 0, 1), hit("b.md", 0, 2)],
      [hit("b.md", 0, 1), hit("a.md", 0, 2)],
      60,
      0.1,
      0.9,
    );
    // b.md domine : rang 1 sur le canal le plus lourd (lexical).
    expect(result[0]?.path).toBe("b.md");
    expect(result[1]?.path).toBe("a.md");
  });
});
