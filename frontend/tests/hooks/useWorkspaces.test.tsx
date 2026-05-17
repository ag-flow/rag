import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import * as apiModule from "@/lib/api";
import {
  useWorkspaces,
  useCreateWorkspace,
  useDeleteWorkspace,
  useRotateApiKey,
  useReindex,
} from "@/hooks/useWorkspaces";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    qc,
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    ),
  };
}

describe("useWorkspaces hooks", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("useWorkspaces fetches the list", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue([
      {
        id: "1",
        name: "ws_a",
        indexer: { provider: "openai", model: "x" },
        sources_count: 0,
        documents_count: 0,
        last_indexed_at: null,
        created_at: "",
      },
    ]);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useWorkspaces(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.[0]?.name).toBe("ws_a");
  });

  it("useCreateWorkspace POSTs and invalidates", async () => {
    vi.spyOn(apiModule.api, "post").mockResolvedValue({ name: "ws_a", api_key: "key-xyz" });

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useCreateWorkspace(), { wrapper });
    result.current.mutate({
      name: "ws_a",
      indexer: { provider: "openai", model: "x", api_key_ref: "k" },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["workspaces"] });
  });

  it("useDeleteWorkspace DELETEs by name", async () => {
    const deleteSpy = vi.spyOn(apiModule.api, "delete").mockResolvedValue({});

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useDeleteWorkspace(), { wrapper });

    result.current.mutate("ws_a");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(deleteSpy).toHaveBeenCalledWith("/api/admin/workspaces/ws_a");
  });

  it("useRotateApiKey POSTs and returns new key", async () => {
    vi.spyOn(apiModule.api, "post").mockResolvedValue({ api_key: "new-key" });

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useRotateApiKey("ws_a"), { wrapper });

    result.current.mutate();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.api_key).toBe("new-key");
  });

  it("useReindex POSTs with ?confirm=true", async () => {
    const postSpy = vi.spyOn(apiModule.api, "post").mockResolvedValue({});

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useReindex("ws_a"), { wrapper });

    result.current.mutate();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(postSpy).toHaveBeenCalledWith(
      "/api/admin/workspaces/ws_a/reindex?confirm=true",
      {},
    );
  });
});
