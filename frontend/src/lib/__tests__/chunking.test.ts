import { describe, it, expect, vi, beforeEach } from "vitest";
import { chunkingApi, isChunkingChangeRequiresReindex } from "@/lib/chunking";
import { api, ApiError } from "@/lib/api";
import type { ChunkingConfig, ChunkingSpec } from "@/lib/chunking.types";

const baseSpec: ChunkingSpec = {
  strategy: "paragraph",
  max_chars: 2000,
  min_chars: 200,
  overlap_chars: 200,
  extras: {},
};

const baseConfig: ChunkingConfig = {
  workspace_id: "ws-1",
  ...baseSpec,
  created_at: "2026-05-19T10:00:00Z",
  updated_at: "2026-05-19T10:00:00Z",
};

describe("chunkingApi.upsert", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("retourne {status: 'no_change'} sur 204", async () => {
    vi.spyOn(api, "putRaw").mockResolvedValue(new Response(null, { status: 204 }));
    const r = await chunkingApi.upsert("ws-1", baseSpec, false);
    expect(r).toEqual({ status: "no_change" });
  });

  it("retourne {status: 'updated', config} sur 200", async () => {
    vi.spyOn(api, "putRaw").mockResolvedValue(
      new Response(JSON.stringify(baseConfig), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const r = await chunkingApi.upsert("ws-1", baseSpec, false);
    expect(r.status).toBe("updated");
    if (r.status === "updated") {
      expect(r.config.workspace_id).toBe("ws-1");
    }
  });

  it("retourne {status: 'reindex_triggered', job} sur 202", async () => {
    const job = {
      id: "job-1",
      triggered_by: "reindex_chunking_change",
      status: "pending",
      files_changed: 0,
      files_skipped: 0,
      error_message: null,
      started_at: null,
      finished_at: null,
      duration_ms: null,
    };
    vi.spyOn(api, "putRaw").mockResolvedValue(
      new Response(JSON.stringify(job), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const r = await chunkingApi.upsert("ws-1", baseSpec, true);
    expect(r.status).toBe("reindex_triggered");
    if (r.status === "reindex_triggered") {
      expect(r.job.triggered_by).toBe("reindex_chunking_change");
    }
  });

  it("propage ApiError sur 409", async () => {
    vi.spyOn(api, "putRaw").mockRejectedValue(
      new ApiError(409, {
        error: "chunking_change_requires_reindex",
        workspace: "ws-1",
        current: "paragraph (max=2000, min=200, overlap=200)",
        new: "paragraph (max=1500, min=100, overlap=150)",
        action: "PUT /workspaces/ws-1/chunking-config?confirm=true",
      }),
    );
    await expect(chunkingApi.upsert("ws-1", baseSpec, false)).rejects.toMatchObject({
      status: 409,
      body: {
        error: "chunking_change_requires_reindex",
        current: expect.any(String),
        new: expect.any(String),
        action: expect.any(String),
      },
    });
  });

  it("URL inclut ?confirm=true quand confirm=true", async () => {
    const putRawSpy = vi
      .spyOn(api, "putRaw")
      .mockResolvedValue(new Response(null, { status: 204 }));
    await chunkingApi.upsert("ws-1", baseSpec, true);
    expect(putRawSpy).toHaveBeenCalledWith(
      "/api/admin/workspaces/ws-1/chunking-config?confirm=true",
      baseSpec,
    );
  });

  it("URL sans query quand confirm=false", async () => {
    const putRawSpy = vi
      .spyOn(api, "putRaw")
      .mockResolvedValue(new Response(null, { status: 204 }));
    await chunkingApi.upsert("ws-1", baseSpec, false);
    expect(putRawSpy).toHaveBeenCalledWith("/api/admin/workspaces/ws-1/chunking-config", baseSpec);
  });
});

describe("isChunkingChangeRequiresReindex", () => {
  it("renvoie true sur le bon shape", () => {
    expect(
      isChunkingChangeRequiresReindex({
        error: "chunking_change_requires_reindex",
        workspace: "ws-1",
        current: "x",
        new: "y",
        action: "z",
      }),
    ).toBe(true);
  });

  it("renvoie false sur autre erreur", () => {
    expect(isChunkingChangeRequiresReindex({ error: "workspace_not_found" })).toBe(false);
  });

  it("renvoie false sur null/non-objet", () => {
    expect(isChunkingChangeRequiresReindex(null)).toBe(false);
    expect(isChunkingChangeRequiresReindex(undefined)).toBe(false);
    expect(isChunkingChangeRequiresReindex("string")).toBe(false);
  });
});
