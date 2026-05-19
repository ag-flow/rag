import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useChunkingConfig, useUpsertChunkingConfig } from "@/hooks/useChunking";
import { chunkingApi } from "@/lib/chunking";
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

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useChunkingConfig", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("fetch et retourne data sur 200", async () => {
    vi.spyOn(chunkingApi, "get").mockResolvedValue(baseConfig);
    const { result } = renderHook(() => useChunkingConfig("ws-1", true), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.workspace_id).toBe("ws-1");
  });

  it("ne fetch pas quand enabled=false", () => {
    const spy = vi.spyOn(chunkingApi, "get").mockResolvedValue(baseConfig);
    renderHook(() => useChunkingConfig("ws-1", false), { wrapper });
    expect(spy).not.toHaveBeenCalled();
  });
});

describe("useUpsertChunkingConfig", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("invalide les queries chunking sur 'updated'", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invSpy = vi.spyOn(qc, "invalidateQueries");
    vi.spyOn(chunkingApi, "upsert").mockResolvedValue({
      status: "updated",
      config: baseConfig,
    });

    function customWrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
    }

    const { result } = renderHook(() => useUpsertChunkingConfig("ws-1"), {
      wrapper: customWrapper,
    });
    await result.current.mutateAsync({ payload: baseSpec, confirm: false });

    expect(invSpy).toHaveBeenCalledWith({
      queryKey: ["workspace", "ws-1", "chunking"],
    });
  });

  it("invalide chunking + jobs sur 'reindex_triggered'", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invSpy = vi.spyOn(qc, "invalidateQueries");
    vi.spyOn(chunkingApi, "upsert").mockResolvedValue({
      status: "reindex_triggered",
      job: {
        id: "j",
        triggered_by: "reindex_chunking_change",
        status: "pending",
        files_changed: 0,
        files_skipped: 0,
        error_message: null,
        started_at: null,
        finished_at: null,
        duration_ms: null,
      },
    });

    function customWrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
    }

    const { result } = renderHook(() => useUpsertChunkingConfig("ws-1"), {
      wrapper: customWrapper,
    });
    await result.current.mutateAsync({ payload: baseSpec, confirm: true });

    expect(invSpy).toHaveBeenCalledWith({
      queryKey: ["workspace", "ws-1", "chunking"],
    });
    expect(invSpy).toHaveBeenCalledWith({
      queryKey: ["workspace", "ws-1", "jobs"],
    });
  });

  it("n'invalide rien sur 'no_change'", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invSpy = vi.spyOn(qc, "invalidateQueries");
    vi.spyOn(chunkingApi, "upsert").mockResolvedValue({ status: "no_change" });

    function customWrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
    }

    const { result } = renderHook(() => useUpsertChunkingConfig("ws-1"), {
      wrapper: customWrapper,
    });
    await result.current.mutateAsync({ payload: baseSpec, confirm: false });

    expect(invSpy).not.toHaveBeenCalled();
  });
});
