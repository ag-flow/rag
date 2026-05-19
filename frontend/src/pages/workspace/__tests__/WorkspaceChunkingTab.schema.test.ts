import { describe, it, expect } from "vitest";
import {
  chunkingFormSchema,
  DEFAULT_CHUNKING_FORM,
} from "@/pages/workspace/WorkspaceChunkingTab.schema";

describe("chunkingFormSchema", () => {
  it("valide les défauts", () => {
    expect(() => chunkingFormSchema.parse(DEFAULT_CHUNKING_FORM)).not.toThrow();
  });

  it("rejette max_chars < 1", () => {
    const r = chunkingFormSchema.safeParse({
      strategy: "paragraph",
      max_chars: 0,
      min_chars: 0,
      overlap_chars: 0,
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(r.error.issues[0]?.path).toContain("max_chars");
    }
  });

  it("rejette min_chars >= max_chars avec message min_lt_max", () => {
    const r = chunkingFormSchema.safeParse({
      strategy: "paragraph",
      max_chars: 200,
      min_chars: 200,
      overlap_chars: 50,
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      const issue = r.error.issues.find((i) => i.path[0] === "min_chars");
      expect(issue?.message).toBe("min_lt_max");
    }
  });

  it("rejette overlap_chars >= max_chars avec message overlap_lt_max", () => {
    const r = chunkingFormSchema.safeParse({
      strategy: "paragraph",
      max_chars: 500,
      min_chars: 100,
      overlap_chars: 500,
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      const issue = r.error.issues.find((i) => i.path[0] === "overlap_chars");
      expect(issue?.message).toBe("overlap_lt_max");
    }
  });

  it("accepte min_chars=0", () => {
    expect(() =>
      chunkingFormSchema.parse({
        strategy: "paragraph",
        max_chars: 1000,
        min_chars: 0,
        overlap_chars: 100,
      }),
    ).not.toThrow();
  });

  it("accepte overlap_chars=0", () => {
    expect(() =>
      chunkingFormSchema.parse({
        strategy: "paragraph",
        max_chars: 1000,
        min_chars: 100,
        overlap_chars: 0,
      }),
    ).not.toThrow();
  });

  it("coerce string → number sur max_chars", () => {
    const r = chunkingFormSchema.parse({
      strategy: "paragraph",
      max_chars: "1500" as unknown as number,
      min_chars: 100,
      overlap_chars: 100,
    });
    expect(r.max_chars).toBe(1500);
  });
});
