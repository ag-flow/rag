import { describe, it, expect } from "vitest";
import { computeExtrasPayload } from "@/lib/chunkingExtras";
import type { ChunkingConfig } from "@/lib/chunking.types";

function makeConfig(overrides: Partial<ChunkingConfig> = {}): ChunkingConfig {
  return {
    workspace_id: "ws-1",
    strategy: "paragraph",
    max_chars: 2000,
    min_chars: 200,
    overlap_chars: 200,
    extras: {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("computeExtrasPayload", () => {
  it("renvoie {} quand paragraph reste paragraph", () => {
    const current = makeConfig({ strategy: "paragraph", extras: {} });
    expect(computeExtrasPayload("paragraph", current)).toEqual({});
  });

  it("renvoie {} en switch paragraph → markdown (backend appliquera son default)", () => {
    const current = makeConfig({ strategy: "paragraph", extras: {} });
    expect(computeExtrasPayload("markdown", current)).toEqual({});
  });

  it("renvoie {} en switch markdown → paragraph (sinon backend rejette)", () => {
    const current = makeConfig({
      strategy: "markdown",
      extras: { heading_levels: [1, 2] },
    });
    expect(computeExtrasPayload("paragraph", current)).toEqual({});
  });

  it("préserve current.extras quand markdown reste markdown (conf admin custom)", () => {
    const current = makeConfig({
      strategy: "markdown",
      extras: { heading_levels: [1, 3] },
    });
    expect(computeExtrasPayload("markdown", current)).toBe(current.extras);
  });
});
