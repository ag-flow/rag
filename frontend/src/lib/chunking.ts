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

export const chunkingApi = {
  get: (name: string) => api.get<ChunkingConfig>(base(name)),

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
