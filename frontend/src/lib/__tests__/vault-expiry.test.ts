import { describe, it, expect } from "vitest";
import { daysUntilExpiry, expiryStatus, worstExpiryStatus } from "@/lib/vault-expiry";
import type { VaultKeyExpiry } from "@/lib/harpocrate-vaults.types";

const DAY_MS = 24 * 60 * 60 * 1000;

function iso(offsetDays: number): string {
  return new Date(Date.now() + offsetDays * DAY_MS).toISOString();
}

function entry(expiresAt: string | null): VaultKeyExpiry {
  return { vault_id: "v", name: "n", label: "l", api_key_expires_at: expiresAt };
}

describe("expiryStatus", () => {
  it("null ou absent → none (token sans expiration ou illisible)", () => {
    expect(expiryStatus(null)).toBe("none");
    expect(expiryStatus(undefined)).toBe("none");
  });

  it("date passée → expired", () => {
    expect(expiryStatus(iso(-1))).toBe("expired");
  });

  it("sous le seuil de 30 jours → expiring", () => {
    expect(expiryStatus(iso(10))).toBe("expiring");
    expect(expiryStatus(iso(29))).toBe("expiring");
  });

  it("au-delà du seuil → ok", () => {
    expect(expiryStatus(iso(45))).toBe("ok");
  });
});

describe("worstExpiryStatus", () => {
  it("expired prime sur expiring qui prime sur ok", () => {
    expect(worstExpiryStatus([entry(iso(45)), entry(iso(-2)), entry(iso(5))])).toBe("expired");
    expect(worstExpiryStatus([entry(iso(45)), entry(iso(5))])).toBe("expiring");
    expect(worstExpiryStatus([entry(iso(45))])).toBe("ok");
  });

  it("liste vide ou sans dates → none", () => {
    expect(worstExpiryStatus([])).toBe("none");
    expect(worstExpiryStatus([entry(null)])).toBe("none");
  });
});

describe("daysUntilExpiry", () => {
  it("arrondit au jour inférieur, jamais négatif", () => {
    expect(daysUntilExpiry(iso(10.5))).toBe(10);
    expect(daysUntilExpiry(iso(-3))).toBe(0);
  });
});
