import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { RevealApiKeyDialog } from "@/pages/workspace/RevealApiKeyDialog";

const mockMutate = vi.fn();

vi.mock("@/hooks/useWorkspaces", () => ({
  useRevealApiKey: () => ({
    mutate: mockMutate,
    isPending: false,
  }),
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

describe("RevealApiKeyDialog", () => {
  it("affiche le titre et l'avertissement quand ouvert", () => {
    renderWithProviders(
      <RevealApiKeyDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    expect(screen.getByText("Révéler la clé API")).toBeInTheDocument();
    expect(screen.getByText(/Affiche la clé API en clair/)).toBeInTheDocument();
  });

  it("affiche les boutons Annuler et Révéler", () => {
    renderWithProviders(
      <RevealApiKeyDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    expect(screen.getByRole("button", { name: /annuler/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^révéler$/i })).toBeInTheDocument();
  });

  it("appelle mutate au clic sur Révéler", () => {
    renderWithProviders(
      <RevealApiKeyDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^révéler$/i }));
    expect(mockMutate).toHaveBeenCalledOnce();
  });

  it("n'affiche rien si fermé", () => {
    renderWithProviders(
      <RevealApiKeyDialog name="my-workspace" open={false} onOpenChange={() => {}} />,
    );
    expect(screen.queryByText("Révéler la clé API")).not.toBeInTheDocument();
  });
});
