import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import * as apiModule from "@/lib/api";
import { useMe } from "@/hooks/useMe";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useMe", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("returns user data on success", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue({
      sub: "user-uuid",
      email: "test@example.com",
      name: "Test User",
      roles: ["rag-admin"],
    });

    const { result } = renderHook(() => useMe(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.email).toBe("test@example.com");
  });

  it("returns error on 401", async () => {
    vi.spyOn(apiModule.api, "get").mockRejectedValue(
      new apiModule.ApiError(401, { error: "oidc_session_missing" }),
    );

    const { result } = renderHook(() => useMe(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(apiModule.isUnauthorized(result.current.error)).toBe(true);
  });
});
