import { api } from "@/lib/api";
import type {
  ChunkingConfig,
  ChunkingSpec,
  ChunkingChangeRequiresReindexBody,
} from "@/lib/chunking.types";
import type { Job } from "@/lib/workspaces.types";

const base = (name: string) => `/api/admin/workspaces/${name}/chunking-config`;

export type UpsertChunkingResult =
  | { status: "no_change" }
  | { status: "updated"; config: ChunkingConfig }
  | { status: "reindex_triggered"; job: Job };

export type SetDefaultStrategyResult =
  | { status: "no_change" }
  | { status: "updated"; default_strategy_id: string | null }
  | { status: "reindex_triggered"; job: Job };

export const chunkingApi = {
  get: (name: string) => api.get<ChunkingConfig>(base(name)),

  /**
   * PUT /chunking-config/default-strategy?confirm= — binding PAR ID de la
   * stratégie par défaut du workspace (spec chunking §5). Même protocole que
   * `upsert` : 204 / 200 / 202, 409 propagé pour le dialog de réindexation.
   */
  setDefaultStrategy: async (
    name: string,
    strategyId: string | null,
    confirm: boolean = false,
  ): Promise<SetDefaultStrategyResult> => {
    const url = `${base(name)}/default-strategy${confirm ? "?confirm=true" : ""}`;
    const res = await api.putRaw(url, { strategy_id: strategyId });
    if (res.status === 204) return { status: "no_change" };
    if (res.status === 200) {
      const body = (await res.json()) as { default_strategy_id: string | null };
      return { status: "updated", default_strategy_id: body.default_strategy_id };
    }
    if (res.status === 202) {
      const job = (await res.json()) as Job;
      return { status: "reindex_triggered", job };
    }
    throw new Error(`Unexpected status ${res.status} from PUT default-strategy`);
  },

  /**
   * PUT /chunking-config?confirm={confirm}.
   * - 204 → no_change
   * - 200 → updated (+ ChunkingConfig)
   * - 202 → reindex_triggered (+ Job)
   * - 409 propage ApiError ; le caller intercepte pour afficher le dialog.
   */
  upsert: async (
    name: string,
    payload: ChunkingSpec,
    confirm: boolean = false,
  ): Promise<UpsertChunkingResult> => {
    const url = confirm ? `${base(name)}?confirm=true` : base(name);
    const res = await api.putRaw(url, payload);
    if (res.status === 204) return { status: "no_change" };
    if (res.status === 200) {
      const config = (await res.json()) as ChunkingConfig;
      return { status: "updated", config };
    }
    if (res.status === 202) {
      const job = (await res.json()) as Job;
      return { status: "reindex_triggered", job };
    }
    throw new Error(`Unexpected status ${res.status} from PUT chunking-config`);
  },
};

export function isChunkingChangeRequiresReindex(
  body: unknown,
): body is ChunkingChangeRequiresReindexBody {
  return (
    typeof body === "object" &&
    body !== null &&
    "error" in body &&
    (body as { error: unknown }).error === "chunking_change_requires_reindex"
  );
}
