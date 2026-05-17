import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { AddSourceDialog } from "@/pages/workspace/AddSourceDialog";

const mockMutate = vi.fn();

vi.mock("@/hooks/useWorkspaces", () => ({
  useAddSource: () => ({
    mutate: mockMutate,
    isPending: false,
  }),
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

describe("AddSourceDialog", () => {
  it("affiche le titre quand ouvert", () => {
    renderWithProviders(
      <AddSourceDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    expect(screen.getByText("Ajouter une source git")).toBeInTheDocument();
  });

  it("affiche les champs URL, Branche, Référence d'authentification", () => {
    renderWithProviders(
      <AddSourceDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    expect(screen.getByText(/^URL$/)).toBeInTheDocument();
    expect(screen.getByText(/^Branche$/)).toBeInTheDocument();
    expect(screen.getByText(/Référence d'authentification/)).toBeInTheDocument();
  });

  it("affiche une erreur de validation si l'URL est invalide", async () => {
    renderWithProviders(
      <AddSourceDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    const urlInput = screen.getByPlaceholderText("https://github.com/...");
    fireEvent.change(urlInput, { target: { value: "not-a-url" } });
    const submitBtn = screen.getByRole("button", { name: /^ajouter$/i });
    fireEvent.click(submitBtn);
    await waitFor(() => {
      expect(screen.getByText("URL invalide.")).toBeInTheDocument();
    });
  });

  it("soumet le formulaire avec une URL valide", async () => {
    renderWithProviders(
      <AddSourceDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    const urlInput = screen.getByPlaceholderText("https://github.com/...");
    fireEvent.change(urlInput, { target: { value: "https://github.com/org/repo" } });
    const submitBtn = screen.getByRole("button", { name: /^ajouter$/i });
    fireEvent.click(submitBtn);
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledOnce();
    });
  });

  it("n'affiche rien si fermé", () => {
    renderWithProviders(
      <AddSourceDialog name="my-workspace" open={false} onOpenChange={() => {}} />,
    );
    expect(screen.queryByText("Ajouter une source git")).not.toBeInTheDocument();
  });
});
