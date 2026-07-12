import { describe, it, expect } from "vitest";
import { computeExtrasPayload, extractCleaningOptions } from "@/lib/chunkingExtras";
import type { ChunkingConfig } from "@/lib/chunking.types";
import type { CleaningOptions } from "@/pages/workspace/CleaningOptionsPanel.schema";
import { DEFAULT_CLEANING_OPTIONS } from "@/pages/workspace/CleaningOptionsPanel.schema";

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

const NONE = DEFAULT_CLEANING_OPTIONS;

describe("extractCleaningOptions", () => {
  it("renvoie tout false quand extras vide", () => {
    expect(extractCleaningOptions({})).toEqual(NONE);
  });

  it("lit les clés true et ignore heading_levels", () => {
    expect(
      extractCleaningOptions({ clean_content: true, strip_html: true, heading_levels: [1, 2] }),
    ).toEqual({
      clean_content: true,
      strip_separators: false,
      strip_boilerplate: false,
      strip_html: true,
    });
  });

  it("traite une valeur non-`true` comme désactivée", () => {
    expect(extractCleaningOptions({ clean_content: "yes" })).toEqual(NONE);
  });
});

describe("computeExtrasPayload", () => {
  it("renvoie {} quand paragraph reste paragraph sans nettoyage", () => {
    const current = makeConfig({ strategy: "paragraph", extras: {} });
    expect(computeExtrasPayload("paragraph", NONE, current)).toEqual({});
  });

  it("porte les options de nettoyage activées (paragraph)", () => {
    const current = makeConfig({ strategy: "paragraph", extras: {} });
    const cleaning: CleaningOptions = { ...NONE, clean_content: true, strip_html: true };
    expect(computeExtrasPayload("paragraph", cleaning, current)).toEqual({
      clean_content: true,
      strip_html: true,
    });
  });

  it("omet heading_levels au switch paragraph → markdown (backend défaut)", () => {
    const current = makeConfig({ strategy: "paragraph", extras: {} });
    expect(computeExtrasPayload("markdown", NONE, current)).toEqual({});
  });

  it("omet heading_levels au switch markdown → paragraph", () => {
    const current = makeConfig({ strategy: "markdown", extras: { heading_levels: [1, 2] } });
    const cleaning: CleaningOptions = { ...NONE, strip_boilerplate: true };
    expect(computeExtrasPayload("paragraph", cleaning, current)).toEqual({
      strip_boilerplate: true,
    });
  });

  it("préserve heading_levels + nettoyage quand markdown reste markdown", () => {
    const current = makeConfig({ strategy: "markdown", extras: { heading_levels: [1, 3] } });
    const cleaning: CleaningOptions = { ...NONE, strip_separators: true };
    expect(computeExtrasPayload("markdown", cleaning, current)).toEqual({
      strip_separators: true,
      heading_levels: [1, 3],
    });
  });
});
