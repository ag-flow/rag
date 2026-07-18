// Statut d'expiration des clés de coffre (alerte proactive, roadmap §alerte).
// Seuil unique partagé entre l'onglet Info (ExpiresCell), la liste des
// coffres, la bannière du détail et la pastille de navigation.

import type { VaultKeyExpiry } from "@/lib/harpocrate-vaults.types";

export const EXPIRY_THRESHOLD_DAYS = 30;

const DAY_MS = 24 * 60 * 60 * 1000;

export type ExpiryStatus = "none" | "ok" | "expiring" | "expired";

export function expiryStatus(expiresAt: string | null | undefined): ExpiryStatus {
  if (!expiresAt) return "none";
  const diffMs = new Date(expiresAt).getTime() - Date.now();
  if (diffMs < 0) return "expired";
  if (diffMs < EXPIRY_THRESHOLD_DAYS * DAY_MS) return "expiring";
  return "ok";
}

export function daysUntilExpiry(expiresAt: string): number {
  return Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / DAY_MS));
}

/** Pire statut de l'agrégat — pilote la pastille de navigation. */
export function worstExpiryStatus(entries: VaultKeyExpiry[]): ExpiryStatus {
  const statuses = entries.map((e) => expiryStatus(e.api_key_expires_at));
  if (statuses.includes("expired")) return "expired";
  if (statuses.includes("expiring")) return "expiring";
  return statuses.includes("ok") ? "ok" : "none";
}
