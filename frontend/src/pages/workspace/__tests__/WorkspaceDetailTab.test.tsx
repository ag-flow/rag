import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { WorkspaceDetailTab } from "@/pages/workspace/WorkspaceDetailTab";
import type { Workspace } from "@/lib/workspaces.types";

const mockMutate = vi.fn();

vi.mock("@/hooks/useWorkspaces", () => ({
  useUpdateApiKeyRef: () => ({
    mutate: mockMutate,
    isPending: false,
  }),
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

const mockWorkspace: Workspace = {
  id: "abc-123",
  name: "my-workspace",
  indexer: {
    provider: "openai",
    model: "text-embedding-3-small",
    api_key_ref: "openai_key",
    base_url: null,
  },
  sources_count: 3,
  documents_count: 150,
  last_indexed_at: null,
  created_at: "2026-01-01T00:00:00Z",
};

describe("WorkspaceDetailTab", () => {
  it("affiche les statistiques du workspace", () => {
    renderWithProviders(
      <WorkspaceDetailTab
        workspace={mockWorkspace}
        onReveal={() => {}}
        onRotate={() => {}}
      />,
    );
    expect(screen.getByText(/3 sources/)).toBeInTheDocument();
    expect(screen.getByText(/150 documents/)).toBeInTheDocument();
  });

  it("affiche le nom et l'id du workspace", () => {
    renderWithProviders(
      <WorkspaceDetailTab
        workspace={mockWorkspace}
        onReveal={() => {}}
        onRotate={() => {}}
      />,
    );
    expect(screen.getByText("my-workspace")).toBeInTheDocument();
    expect(screen.getByText("abc-123")).toBeInTheDocument();
  });

  it("le bouton Enregistrer est désactivé initialement (non-dirty)", () => {
    renderWithProviders(
      <WorkspaceDetailTab
        workspace={mockWorkspace}
        onReveal={() => {}}
        onRotate={() => {}}
      />,
    );
    const saveBtn = screen.getByRole("button", { name: /enregistrer/i });
    expect(saveBtn).toBeDisabled();
  });

  it("affiche le champ api_key_ref avec la valeur initiale", () => {
    renderWithProviders(
      <WorkspaceDetailTab
        workspace={mockWorkspace}
        onReveal={() => {}}
        onRotate={() => {}}
      />,
    );
    const input = screen.getByRole<HTMLInputElement>("textbox");
    expect(input.value).toBe("openai_key");
  });

  it("déclenche onReveal au click sur Révéler", () => {
    const onReveal = vi.fn();
    renderWithProviders(
      <WorkspaceDetailTab
        workspace={mockWorkspace}
        onReveal={onReveal}
        onRotate={() => {}}
      />,
    );
    screen.getByRole("button", { name: /révéler/i }).click();
    expect(onReveal).toHaveBeenCalledOnce();
  });
});
