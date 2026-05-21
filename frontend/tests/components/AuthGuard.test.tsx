import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { AuthGuard } from "@/components/AuthGuard";
import * as apiModule from "@/lib/api";

const _origLocation = window.location;

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("AuthGuard", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    // Mock window.location pour vérifier le redirect
    delete (window as unknown as { location?: Location }).location;
    (window as unknown as { location: Location }).location = {
      ..._origLocation,
      href: "/ui/workspaces",
      pathname: "/ui/workspaces",
      search: "",
    } as unknown as Location;
  });

  it("shows loading spinner while fetching /me", () => {
    vi.spyOn(apiModule.api, "get").mockImplementation(() => new Promise(() => {}));

    render(
      <Wrapper>
        <AuthGuard>
          <div>child</div>
        </AuthGuard>
      </Wrapper>,
    );

    expect(screen.queryByText("child")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders children when /me succeeds", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue({
      sub: "u", email: "e@x.com", name: "X", roles: ["rag-admin"],
    });

    render(
      <Wrapper>
        <AuthGuard>
          <div>child</div>
        </AuthGuard>
      </Wrapper>,
    );

    await waitFor(() => expect(screen.getByText("child")).toBeInTheDocument());
  });

  it("redirects to /ui/login on 401 (strip /ui prefix from next)", async () => {
    vi.spyOn(apiModule.api, "get").mockRejectedValue(
      new apiModule.ApiError(401, { error: "oidc_session_missing" }),
    );

    render(
      <Wrapper>
        <AuthGuard>
          <div>child</div>
        </AuthGuard>
      </Wrapper>,
    );

    await waitFor(() => {
      expect(window.location.href).toBe(
        "/ui/login?next=" + encodeURIComponent("/workspaces"),
      );
    });
  });
});
