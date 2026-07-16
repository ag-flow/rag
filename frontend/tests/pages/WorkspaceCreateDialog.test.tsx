import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import i18n from "@/lib/i18n";
import { CreateWorkspaceDialog } from "@/pages/workspace/CreateWorkspaceDialog";
import type { VaultWithEndpoints } from "@/hooks/useVaultEndpoints";

const createMutateAsync = vi.fn();

vi.mock("@/hooks/useWorkspaces", () => ({
  useCreateWorkspace: () => ({ mutateAsync: createMutateAsync, isPending: false }),
}));

vi.mock("@/hooks/useVaultEndpoints", () => ({
  useAllVaultEndpoints: vi.fn(),
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import { useAllVaultEndpoints } from "@/hooks/useVaultEndpoints";

const GROUPED: VaultWithEndpoints[] = [
  {
    vault: {
      id: "v-1",
      name: "rag",
      label: "Coffre RAG",
      base_url: "https://vault.example",
      api_key_id: "k-001",
      probe_path: null,
      is_default: true,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
    endpoints: [
      {
        id: "ep-1",
        vault_id: "v-1",
        label: "Docs OpenAI",
        slug: "docs-openai",
        indexer: {
          provider: "openai",
          model: "text-embedding-3-small",
          api_key_ref: "ref",
          base_url: null,
        },
        rerank: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ],
  },
];

function mockEndpoints(data: VaultWithEndpoints[]): void {
  vi.mocked(useAllVaultEndpoints).mockReturnValue({
    data,
    isLoading: false,
  } as unknown as ReturnType<typeof useAllVaultEndpoints>);
}

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

describe("CreateWorkspaceDialog (endpoint-based)", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("fr");
  });

  it("affiche nom + sélecteur d'endpoint (unique pré-sélectionné)", () => {
    mockEndpoints(GROUPED);
    render(
      <Wrapper>
        <CreateWorkspaceDialog open onOpenChange={() => {}} />
      </Wrapper>,
    );
    expect(screen.getByPlaceholderText("mon-projet")).toBeInTheDocument();
    // endpoint unique → pré-sélectionné et visible dans le trigger
    expect(screen.getByText(/Docs OpenAI — openai\/text-embedding-3-small/)).toBeInTheDocument();
  });

  it("soumet {name, endpoint_id}", async () => {
    mockEndpoints(GROUPED);
    createMutateAsync.mockResolvedValue({ name: "mon-ws" });
    render(
      <Wrapper>
        <CreateWorkspaceDialog open onOpenChange={() => {}} />
      </Wrapper>,
    );
    fireEvent.change(screen.getByPlaceholderText("mon-projet"), {
      target: { value: "mon-ws" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Créer$/i }));
    await waitFor(() =>
      expect(createMutateAsync).toHaveBeenCalledWith({
        name: "mon-ws",
        endpoint_id: "ep-1",
      }),
    );
  });

  it("sans endpoint : bouton Créer bloqué + lien vers les coffres", () => {
    mockEndpoints([]);
    render(
      <Wrapper>
        <CreateWorkspaceDialog open onOpenChange={() => {}} />
      </Wrapper>,
    );
    expect(screen.getByText(/Aucun endpoint défini/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Créer$/i })).toBeDisabled();
  });

  it("nom invalide (majuscules) : bouton Créer bloqué", () => {
    mockEndpoints(GROUPED);
    render(
      <Wrapper>
        <CreateWorkspaceDialog open onOpenChange={() => {}} />
      </Wrapper>,
    );
    fireEvent.change(screen.getByPlaceholderText("mon-projet"), {
      target: { value: "MonWS" },
    });
    expect(screen.getByRole("button", { name: /^Créer$/i })).toBeDisabled();
  });
});
