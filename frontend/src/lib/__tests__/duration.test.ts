import { describe, it, expect } from "vitest";
import { formatDurationMs } from "@/lib/duration";

describe("formatDurationMs", () => {
  it("null → tiret (job non terminé ou rejet)", () => {
    expect(formatDurationMs(null)).toBe("—");
  });

  it("sous la seconde → millisecondes", () => {
    expect(formatDurationMs(240)).toBe("240 ms");
  });

  it("sous la minute → secondes avec une décimale", () => {
    expect(formatDurationMs(1200)).toBe("1.2 s");
    expect(formatDurationMs(59_940)).toBe("59.9 s");
  });

  it("au-delà de la minute → min + s sur deux chiffres", () => {
    expect(formatDurationMs(125_000)).toBe("2 min 05 s");
    expect(formatDurationMs(3_600_000)).toBe("60 min 00 s");
  });
});
