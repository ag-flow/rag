import type { ChunkingConfig, ChunkingStrategy } from "@/lib/chunking.types";
import {
  CLEANING_KEYS,
  DEFAULT_CLEANING_OPTIONS,
  type CleaningOptions,
} from "@/pages/workspace/CleaningOptionsPanel.schema";

/**
 * Extrait les options de nettoyage depuis le champ `extras` d'une config.
 * Toute clé absente ou non-`true` est considérée désactivée.
 */
export function extractCleaningOptions(extras: Record<string, unknown>): CleaningOptions {
  const options = { ...DEFAULT_CLEANING_OPTIONS };
  for (const key of CLEANING_KEYS) {
    options[key] = extras[key] === true;
  }
  return options;
}

/**
 * Calcule le payload `extras` à envoyer au PUT /chunking-config.
 *
 * - Les options de nettoyage activées sont toujours portées (indépendantes de
 *   la stratégie ; le backend les accepte pour paragraph et markdown).
 * - `heading_levels` n'est conservé que si la stratégie reste `markdown`
 *   (préserve une conf admin custom) ; sur changement de stratégie il est omis
 *   et le backend applique son défaut ({heading_levels:[1,2]} pour markdown,
 *   rien pour paragraph).
 */
export function computeExtrasPayload(
  nextStrategy: ChunkingStrategy,
  cleaning: CleaningOptions,
  current: ChunkingConfig,
): Record<string, unknown> {
  const extras: Record<string, unknown> = {};
  for (const key of CLEANING_KEYS) {
    if (cleaning[key]) extras[key] = true;
  }
  if (nextStrategy === "markdown" && current.strategy === "markdown") {
    const headingLevels = current.extras.heading_levels;
    if (headingLevels !== undefined) extras.heading_levels = headingLevels;
  }
  return extras;
}
