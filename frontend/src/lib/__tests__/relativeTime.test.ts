import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { relativeTimeKey, formatRelativeTime } from "@/lib/relativeTime";

const NOW = new Date("2026-05-20T12:00:00Z").getTime();

function isoAgo(ms: number): string {
  return new Date(NOW - ms).toISOString();
}

describe("relativeTimeKey", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => vi.useRealTimers());

  it("renvoie time.justNow pour diff = 0", () => {
    expect(relativeTimeKey(isoAgo(0))).toEqual({
      key: "time.justNow",
      count: 0,
    });
  });

  it("renvoie time.justNow pour 30 secondes (< 1 minute)", () => {
    expect(relativeTimeKey(isoAgo(30_000))).toEqual({
      key: "time.justNow",
      count: 0,
    });
  });

  it("renvoie time.minutesAgo pour exactement 1 minute", () => {
    expect(relativeTimeKey(isoAgo(60_000))).toEqual({
      key: "time.minutesAgo",
      count: 1,
    });
  });

  it("renvoie time.minutesAgo pour 59 minutes", () => {
    expect(relativeTimeKey(isoAgo(59 * 60_000))).toEqual({
      key: "time.minutesAgo",
      count: 59,
    });
  });

  it("renvoie time.hoursAgo pour exactement 1 heure", () => {
    expect(relativeTimeKey(isoAgo(60 * 60_000))).toEqual({
      key: "time.hoursAgo",
      count: 1,
    });
  });

  it("renvoie time.hoursAgo pour 23 heures", () => {
    expect(relativeTimeKey(isoAgo(23 * 60 * 60_000))).toEqual({
      key: "time.hoursAgo",
      count: 23,
    });
  });

  it("renvoie time.daysAgo pour exactement 1 jour", () => {
    expect(relativeTimeKey(isoAgo(24 * 60 * 60_000))).toEqual({
      key: "time.daysAgo",
      count: 1,
    });
  });
});

describe("formatRelativeTime", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => vi.useRealTimers());

  it("appelle t sans options pour justNow", () => {
    const t = vi.fn((key: string) => `[${key}]`);
    const result = formatRelativeTime(isoAgo(0), t);
    expect(t).toHaveBeenCalledWith("time.justNow");
    expect(t).toHaveBeenCalledTimes(1);
    expect(result).toBe("[time.justNow]");
  });

  it("appelle t avec count pour minutesAgo (30 min)", () => {
    const t = vi.fn((key: string, opts?: { count: number }) =>
      opts ? `[${key} ${opts.count}]` : `[${key}]`,
    );
    const result = formatRelativeTime(isoAgo(30 * 60_000), t);
    expect(t).toHaveBeenCalledWith("time.minutesAgo", { count: 30 });
    expect(result).toBe("[time.minutesAgo 30]");
  });

  it("appelle t avec count pour daysAgo (5 jours)", () => {
    const t = vi.fn((key: string, opts?: { count: number }) =>
      opts ? `[${key} ${opts.count}]` : `[${key}]`,
    );
    const result = formatRelativeTime(isoAgo(5 * 24 * 60 * 60_000), t);
    expect(t).toHaveBeenCalledWith("time.daysAgo", { count: 5 });
    expect(result).toBe("[time.daysAgo 5]");
  });
});
