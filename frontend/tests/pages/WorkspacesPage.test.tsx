import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import i18n from "@/lib/i18n";
import { WorkspacesPage } from "@/pages/WorkspacesPage";
import * as apiModule from "@/lib/api";

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("WorkspacesPage", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    await i18n.changeLanguage("fr");
  });

  it("shows empty state when workspaces list is empty", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue([]);

    render(<WorkspacesPage />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByText(/aucun workspace/i)).toBeInTheDocument();
    });
  });

  it("renders the table with workspaces data", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue([
      {
        id: "1",
        name: "harpocrate",
        indexer: { provider: "openai", model: "text-embedding-3-small" },
        sources_count: 3,
        documents_count: 412,
        last_indexed_at: "2026-05-16T10:00:00Z",
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);

    render(<WorkspacesPage />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByText("harpocrate")).toBeInTheDocument();
      expect(screen.getByText("412")).toBeInTheDocument();
      expect(screen.getByText(/openai\/text-embedding-3-small/)).toBeInTheDocument();
    });
  });
});
