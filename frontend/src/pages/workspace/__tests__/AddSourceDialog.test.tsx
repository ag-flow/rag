import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { AddSourceDialog } from "@/pages/workspace/AddSourceDialog";

const mockMutate = vi.fn();

vi.mock("@/hooks/useWorkspaces", () => ({
  useAddSource: () => ({ mutate: mockMutate, isPending: false }),
  useUpdateSource: () => ({ mutate: vi.fn(), isPending: false }),
  useTestSourceConnection: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/hooks/useHarpocrateVaults", () => ({
  useVaults: () => ({
    data: [{ name: "vault-default", label: "Default Vault", api_key_id: "key-1" }],
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

  it("affiche les champs Nom, Coffre, URL, Branche, Token", () => {
    renderWithProviders(
      <AddSourceDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    expect(screen.getByText(/Nom de la source/)).toBeInTheDocument();
    expect(screen.getByText(/Coffre Harpocrate/)).toBeInTheDocument();
    expect(screen.getByText(/^URL$/)).toBeInTheDocument();
    expect(screen.getByText(/^Branche$/)).toBeInTheDocument();
    expect(screen.getByText(/Token GitHub/)).toBeInTheDocument();
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
    fireEvent.change(screen.getByPlaceholderText(/ex\. mon-repo/), {
      target: { value: "my-repo" },
    });
    fireEvent.change(screen.getByPlaceholderText("https://github.com/..."), {
      target: { value: "https://github.com/org/repo" },
    });
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

  it("affiche le lien vers GitHub PAT", () => {
    renderWithProviders(
      <AddSourceDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    const link = screen.getByRole("link", { name: /Générer un token GitHub/i });
    expect(link).toHaveAttribute("href", "https://github.com/settings/tokens/new");
    expect(link).toHaveAttribute("target", "_blank");
  });
});
