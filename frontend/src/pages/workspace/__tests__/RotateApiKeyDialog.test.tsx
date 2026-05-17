import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { RotateApiKeyDialog } from "@/pages/workspace/RotateApiKeyDialog";

const mockMutate = vi.fn();

vi.mock("@/hooks/useWorkspaces", () => ({
  useRotateApiKey: () => ({
    mutate: mockMutate,
    isPending: false,
  }),
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

describe("RotateApiKeyDialog", () => {
  it("affiche le titre et l'avertissement quand ouvert", () => {
    renderWithProviders(
      <RotateApiKeyDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    expect(screen.getByText("Régénérer la clé API")).toBeInTheDocument();
    expect(screen.getByText(/invalide immédiatement/)).toBeInTheDocument();
  });

  it("le bouton Régénérer est désactivé si le champ de confirmation est vide", () => {
    renderWithProviders(
      <RotateApiKeyDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    const confirmBtn = screen.getByRole("button", { name: /^régénérer$/i });
    expect(confirmBtn).toBeDisabled();
  });

  it("le bouton Régénérer est désactivé si le nom tapé ne correspond pas", () => {
    renderWithProviders(
      <RotateApiKeyDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    const input = screen.getByPlaceholderText("my-workspace");
    fireEvent.change(input, { target: { value: "wrong-name" } });
    const confirmBtn = screen.getByRole("button", { name: /^régénérer$/i });
    expect(confirmBtn).toBeDisabled();
  });

  it("le bouton Régénérer est activé quand le nom correct est tapé", () => {
    renderWithProviders(
      <RotateApiKeyDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    const input = screen.getByPlaceholderText("my-workspace");
    fireEvent.change(input, { target: { value: "my-workspace" } });
    const confirmBtn = screen.getByRole("button", { name: /^régénérer$/i });
    expect(confirmBtn).not.toBeDisabled();
  });

  it("appelle mutate quand le nom est correct et Régénérer est cliqué", () => {
    renderWithProviders(
      <RotateApiKeyDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    const input = screen.getByPlaceholderText("my-workspace");
    fireEvent.change(input, { target: { value: "my-workspace" } });
    fireEvent.click(screen.getByRole("button", { name: /^régénérer$/i }));
    expect(mockMutate).toHaveBeenCalledOnce();
  });
});
