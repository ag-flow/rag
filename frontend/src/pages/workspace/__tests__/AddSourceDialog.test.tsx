import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { AddSourceDialog } from "@/pages/workspace/AddSourceDialog";

const { mockMutate, mockToast, mockAddResponse } = vi.hoisted(() => ({
  mockMutate: vi.fn(),
  mockToast: vi.fn(),
  mockAddResponse: { value: { id: "s1", branch_warning: null as string | null } },
}));

vi.mock("@/hooks/useWorkspaces", () => ({
  useAddSource: () => ({
    mutate: (payload: unknown, opts?: { onSuccess?: (d: unknown) => void }) => {
      mockMutate(payload);
      opts?.onSuccess?.(mockAddResponse.value);
    },
    isPending: false,
  }),
  useUpdateSource: () => ({ mutate: vi.fn(), isPending: false }),
  useTestSourceConnection: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/hooks/useHarpocrateVaults", () => ({
  useVaults: () => ({
    data: [{ name: "vault-default", label: "Default Vault", api_key_id: "key-1" }],
  }),
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: mockToast }),
}));

describe("AddSourceDialog", () => {
  beforeEach(() => {
    mockMutate.mockClear();
    mockToast.mockClear();
    mockAddResponse.value = { id: "s1", branch_warning: null };
  });

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

  it("laisse la branche undefined quand le champ est vide", async () => {
    renderWithProviders(
      <AddSourceDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    fireEvent.change(screen.getByPlaceholderText(/ex\. mon-repo/), {
      target: { value: "my-repo" },
    });
    fireEvent.change(screen.getByPlaceholderText("https://github.com/..."), {
      target: { value: "https://github.com/org/repo" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^ajouter$/i }));
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledOnce();
    });
    const payload = mockMutate.mock.calls[0]![0] as { config: { branch?: string } };
    expect(payload.config.branch).toBeUndefined();
  });

  it("transmet la branche quand elle est saisie", async () => {
    renderWithProviders(
      <AddSourceDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    fireEvent.change(screen.getByPlaceholderText(/ex\. mon-repo/), {
      target: { value: "my-repo" },
    });
    fireEvent.change(screen.getByPlaceholderText("https://github.com/..."), {
      target: { value: "https://github.com/org/repo" },
    });
    fireEvent.change(screen.getByPlaceholderText(/branche par défaut/i), {
      target: { value: "develop" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^ajouter$/i }));
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledOnce();
    });
    const payload = mockMutate.mock.calls[0]![0] as { config: { branch?: string } };
    expect(payload.config.branch).toBe("develop");
  });

  it("affiche un toast d'avertissement quand branch_warning est présent", async () => {
    mockAddResponse.value = { id: "s1", branch_warning: "w" };
    renderWithProviders(
      <AddSourceDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    fireEvent.change(screen.getByPlaceholderText(/ex\. mon-repo/), {
      target: { value: "my-repo" },
    });
    fireEvent.change(screen.getByPlaceholderText("https://github.com/..."), {
      target: { value: "https://github.com/org/repo" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^ajouter$/i }));
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledOnce();
    });
    // deux toasts : avertissement (branch_warning) + succès
    expect(mockToast).toHaveBeenCalledTimes(2);
  });
});
