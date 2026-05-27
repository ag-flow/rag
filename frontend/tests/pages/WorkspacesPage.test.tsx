import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import i18n from "@/lib/i18n";
import { WorkspacesPage } from "@/pages/WorkspacesPage";
import * as workspacesHooks from "@/hooks/useWorkspaces";

// Mock sous-composants lourds pour isoler WorkspacesPage
vi.mock("@/pages/workspace/WorkspaceDetailPanel", () => ({
  WorkspaceDetailPanel: ({ name }: { name: string }) => (
    <div data-testid="detail-panel">{name}</div>
  ),
}));

vi.mock("@/pages/workspace/CreateWorkspaceDialog", () => ({
  CreateWorkspaceDialog: () => null,
}));

const mockWorkspace = {
  id: "1",
  name: "harpocrate",
  indexer: {
    provider: "openai",
    model: "text-embedding-3-small",
    api_key_ref: null,
    base_url: null,
  },
  sources_count: 3,
  documents_count: 412,
  last_indexed_at: "2026-05-16T10:00:00Z",
  created_at: "2026-01-01T00:00:00Z",
};

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
    vi.spyOn(workspacesHooks, "useWorkspaces").mockReturnValue({
      data: [],
      isLoading: false,
    } as unknown as ReturnType<typeof workspacesHooks.useWorkspaces>);

    render(<WorkspacesPage />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByText(/aucun workspace/i)).toBeInTheDocument();
    });
  });

  it("affiche le nom du workspace dans la liste", async () => {
    vi.spyOn(workspacesHooks, "useWorkspaces").mockReturnValue({
      data: [mockWorkspace],
      isLoading: false,
    } as unknown as ReturnType<typeof workspacesHooks.useWorkspaces>);

    render(<WorkspacesPage />, { wrapper: Wrapper });

    await waitFor(() => {
      // Le workspace name apparaît (potentiellement plusieurs fois : liste + detail panel)
      const matches = screen.getAllByText("harpocrate");
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });
  });
});
