import type { ChunkingConfig, ChunkingStrategy } from "@/lib/chunking.types";

/**
 * Calcule le payload `extras` a envoyer au PUT /chunking-config.
 *
 * - Si la strategy change -> renvoie {} (le backend applique son default,
 *   notamment {heading_levels:[1,2]} pour markdown).
 * - Si la strategy ne change pas -> renvoie current.extras tel quel
 *   (preserve un heading_levels custom pose via API admin).
 */
export function computeExtrasPayload(
  nextStrategy: ChunkingStrategy,
  current: ChunkingConfig,
): Record<string, unknown> {
  return nextStrategy === current.strategy ? current.extras : {};
}
