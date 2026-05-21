import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { WorkspaceSourcesTab } from "@/pages/workspace/WorkspaceSourcesTab";

vi.mock("@/hooks/useWorkspaces", () => ({
  useWorkspaceSources: () => ({
    data: [
      {
        id: "src-1",
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
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

describe("WorkspaceSourcesTab", () => {
  it("affiche la liste des sources", () => {
    renderWithProviders(<WorkspaceSourcesTab name="my-workspace" enabled={true} />);
    expect(screen.getByText("https://github.com/org/repo")).toBeInTheDocument();
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
    // Après expand, les champs détail apparaissent
    expect(screen.getByText(/Référence d'authentification/i)).toBeInTheDocument();
  });

  it("affiche le bouton Ajouter une source", () => {
    renderWithProviders(<WorkspaceSourcesTab name="my-workspace" enabled={true} />);
    expect(screen.getByText("Ajouter une source")).toBeInTheDocument();
  });
});
