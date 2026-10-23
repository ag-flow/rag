import { ApiError } from "@/lib/api";

/** Raisons de refus renvoyées par le backend au départ (détail du 409). */
const KNOWN_START_ERRORS = new Set([
  "name_taken",
  "https_required",
  "client_not_declared",
  "redirect_uri_not_declared",
  "harpocrate_unreachable",
  "exchange_failed",
]);

/** Ce qu'il faut déclarer chez Harpocrate, renvoyé avec les refus de déclaration. */
export interface Declaration {
  client_id: string;
  redirect_uri: string;
}

/**
 * Départ « Connecter » ou « Reconnecter » refusé : le 409 porte soit une
 * raison seule, soit `{reason, client_id, redirect_uri}`.
 */
export function parseStartError(err: unknown): { key: string; declaration: Declaration | null } {
  const detail = err instanceof ApiError ? (err.body as { detail?: unknown } | null)?.detail : null;
  if (typeof detail === "string") {
    return { key: KNOWN_START_ERRORS.has(detail) ? detail : "generic", declaration: null };
  }
  if (detail && typeof detail === "object") {
    const d = detail as Partial<Declaration> & { reason?: unknown };
    if (typeof d.reason === "string" && KNOWN_START_ERRORS.has(d.reason)) {
      const declaration =
        typeof d.client_id === "string" && typeof d.redirect_uri === "string"
          ? { client_id: d.client_id, redirect_uri: d.redirect_uri }
          : null;
      return { key: d.reason, declaration };
    }
  }
  return { key: "generic", declaration: null };
}
