import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { WorkspaceSourcesTab } from "@/pages/workspace/WorkspaceSourcesTab";

vi.mock("@/hooks/useWorkspaces", () => ({
  useWorkspaceSources: () => ({
    data: [
      {
        id: "src-1",
        name: "mon-repo",
        type: "git",
        config: {
          url: "https://github.com/org/repo",
          branch: "main",
          auth_ref: null,
          include: [],
          exclude: [],
        },
        last_indexed_at: null,
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
    isLoading: false,
  }),
  useAddSource: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateSource: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteSource: () => ({ mutate: vi.fn(), isPending: false }),
  useTestSourceConnection: () => ({ mutate: vi.fn(), isPending: false }),
  useTriggerSourceSync: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/hooks/useJobLogs", () => ({
  useJobLogs: () => ({ lines: [], jobStatus: "idle" }),
}));

vi.mock("@/hooks/useHarpocrateVaults", () => ({
  useVaults: () => ({ data: [] }),
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

describe("WorkspaceSourcesTab", () => {
  it("affiche la liste des sources", () => {
    renderWithProviders(<WorkspaceSourcesTab name="my-workspace" enabled={true} />);
    expect(screen.getByText("https://github.com/org/repo")).toBeInTheDocument();
  });

  it("affiche le nom de la source dans le header", () => {
    renderWithProviders(<WorkspaceSourcesTab name="my-workspace" enabled={true} />);
    expect(screen.getByText("mon-repo")).toBeInTheDocument();
  });

  it("affiche le titre avec le count", () => {
    renderWithProviders(<WorkspaceSourcesTab name="my-workspace" enabled={true} />);
    expect(screen.getByText(/Sources git \(1\)/)).toBeInTheDocument();
  });

  it("ouvre le détail de la source au clic (accordion)", () => {
    renderWithProviders(<WorkspaceSourcesTab name="my-workspace" enabled={true} />);
    const urlEl = screen.getByText("https://github.com/org/repo");
    const row = urlEl.closest("button");
    expect(row).not.toBeNull();
    fireEvent.click(row!);
    expect(screen.getByText(/aucune authentification/i)).toBeInTheDocument();
  });

  it("affiche le bouton Ajouter une source", () => {
    renderWithProviders(<WorkspaceSourcesTab name="my-workspace" enabled={true} />);
    expect(screen.getByText("Ajouter une source")).toBeInTheDocument();
  });
});
