import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "@/lib/i18n";
import { CreateWorkspaceDialog as WorkspaceCreateDialog } from "@/pages/workspace/CreateWorkspaceDialog";
import * as apiModule from "@/lib/api";

// Mock useVaults : fournit un coffre disponible pour que le Select s'affiche
// et que le bouton Créer ne soit pas désactivé.
vi.mock("@/hooks/useHarpocrateVaults", () => ({
  useVaults: () => ({
    data: [
      {
        id: "vault-1",
        name: "vault-main",
        label: "Coffre principal",
        base_url: "http://localhost:8200",
        api_key_id: "key-id",
        probe_path: null,
        is_default: true,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ],
    isLoading: false,
  }),
}));

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("WorkspaceCreateDialog", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    // Restaure le mock useVaults après restoreAllMocks
    vi.mock("@/hooks/useHarpocrateVaults", () => ({
      useVaults: () => ({
        data: [
          {
            id: "vault-1",
            name: "vault-main",
            label: "Coffre principal",
            base_url: "http://localhost:8200",
            api_key_id: "key-id",
            probe_path: null,
            is_default: true,
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
        ],
        isLoading: false,
      }),
    }));
    await i18n.changeLanguage("fr");
  });

  it("renders form fields when open", () => {
    render(
      <Wrapper>
        <WorkspaceCreateDialog open={true} onOpenChange={() => {}} />
      </Wrapper>,
    );

    // Name input — FormLabel htmlFor wired via FormItem id
    expect(screen.getByPlaceholderText("harpocrate")).toBeInTheDocument();
    // Provider, model and vault selects rendered as combobox buttons
    const comboboxes = screen.getAllByRole("combobox");
    expect(comboboxes.length).toBeGreaterThanOrEqual(3);
    // api_key_ref present by default (provider = openai)
    expect(screen.getByPlaceholderText("openai_embedding_key")).toBeInTheDocument();
  });

  it("shows base_url field only for ollama provider, not api_key_ref", () => {
    render(
      <Wrapper>
        <WorkspaceCreateDialog open={true} onOpenChange={() => {}} />
      </Wrapper>,
    );

    // Initially openai → api_key_ref visible, base_url not
    expect(screen.getByPlaceholderText("openai_embedding_key")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("http://192.168.10.80:11434")).not.toBeInTheDocument();

    // Simulate provider change to ollama via the hidden select input
    // Radix Select renders a native <select> in the DOM for form compatibility
    // Le premier native select est le coffre vault, le second est le provider
    const nativeSelects = document.querySelectorAll("select");
    // Le select provider est le second (après le vault select)
    const providerSelect = nativeSelects[1];
    expect(providerSelect).toBeDefined();
    fireEvent.change(providerSelect!, { target: { value: "ollama" } });

    // After switching to ollama → base_url visible, api_key_ref gone
    expect(screen.getByPlaceholderText("http://192.168.10.80:11434")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("openai_embedding_key")).not.toBeInTheDocument();
  });

  it("submits valid form and calls api.post", async () => {
    const postSpy = vi
      .spyOn(apiModule.api, "post")
      .mockResolvedValue({ name: "test_ws", api_key: "key" });
    const user = userEvent.setup();
    const onOpenChange = vi.fn();

    render(
      <Wrapper>
        <WorkspaceCreateDialog open={true} onOpenChange={onOpenChange} />
      </Wrapper>,
    );

    await user.type(screen.getByPlaceholderText("harpocrate"), "test_ws");
    await user.type(screen.getByPlaceholderText("openai_embedding_key"), "openai_key");

    // Sélectionner le coffre via le native select (Radix Select)
    const nativeSelects = document.querySelectorAll("select");
    const vaultSelect = nativeSelects[0];
    fireEvent.change(vaultSelect!, { target: { value: "vault-main" } });

    await user.click(screen.getByRole("button", { name: /créer/i }));

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith(
        "/api/admin/workspaces",
        expect.objectContaining({
          name: "test_ws",
          api_key_vault: "vault-main",
          indexer: expect.objectContaining({
            provider: "openai",
            api_key_ref: "openai_key",
          }),
        }),
      );
    });
  });

  it("validates name format (lowercase only)", async () => {
    const user = userEvent.setup();
    render(
      <Wrapper>
        <WorkspaceCreateDialog open={true} onOpenChange={() => {}} />
      </Wrapper>,
    );

    // Sélectionner un coffre pour ne pas bloquer la soumission sur ce champ
    const nativeSelects = document.querySelectorAll("select");
    const vaultSelect = nativeSelects[0];
    fireEvent.change(vaultSelect!, { target: { value: "vault-main" } });

    await user.type(screen.getByPlaceholderText("harpocrate"), "BadName");
    await user.type(screen.getByPlaceholderText("openai_embedding_key"), "key");
    await user.click(screen.getByRole("button", { name: /créer/i }));

    await waitFor(() => {
      expect(screen.getByText(/name_invalid_format/i)).toBeInTheDocument();
    });
  });
});
