import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "@/lib/i18n";
import { CreateVaultDialog } from "@/pages/harpocrate/CreateVaultDialog";
import * as apiModule from "@/lib/api";
import { ApiError } from "@/lib/api";

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByPlaceholderText(/rag, prod-eu/i), "rag");
  await user.type(screen.getByPlaceholderText(/coffre rag production/i), "Coffre RAG");
  await user.type(screen.getByPlaceholderText(/vault\.yoops\.org/i), "https://vault.yoops.org");
  await user.type(screen.getByPlaceholderText(/k-001/i), "k-001");
  await user.type(screen.getByPlaceholderText(/hrpv_1_/i), "hrpv_1_secret_token_value");
}

describe("CreateVaultDialog", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    await i18n.changeLanguage("fr");
  });

  it("submits the form and calls onCreated on success", async () => {
    const created = {
      id: "v-new",
      name: "rag",
      label: "Coffre RAG",
      base_url: "https://vault.yoops.org",
      api_key_id: "k-001",
      probe_path: null,
      is_default: true,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    const postSpy = vi.spyOn(apiModule.api, "post").mockResolvedValue(created);
    const onCreated = vi.fn();
    const user = userEvent.setup();

    render(
      <Wrapper>
        <CreateVaultDialog open={true} onOpenChange={() => {}} onCreated={onCreated} />
      </Wrapper>,
    );

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /créer le coffre/i }));

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith(
        "/api/admin/harpocrate-vaults",
        expect.objectContaining({ name: "rag", api_key_id: "k-001" }),
      );
      expect(onCreated).toHaveBeenCalledWith(created);
    });
  });

  it("shows the name_taken error on HTTP 409", async () => {
    vi.spyOn(apiModule.api, "post").mockRejectedValue(
      new ApiError(409, { detail: "name_taken" }),
    );
    const user = userEvent.setup();

    render(
      <Wrapper>
        <CreateVaultDialog open={true} onOpenChange={() => {}} onCreated={() => {}} />
      </Wrapper>,
    );

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /créer le coffre/i }));

    await waitFor(() => {
      expect(screen.getByText(/ce nom est déjà utilisé/i)).toBeInTheDocument();
    });
  });

  it("renders the DEK missing panel on HTTP 503", async () => {
    vi.spyOn(apiModule.api, "post").mockRejectedValue(
      new ApiError(503, { detail: "dek_missing" }),
    );
    const user = userEvent.setup();

    render(
      <Wrapper>
        <CreateVaultDialog open={true} onOpenChange={() => {}} onCreated={() => {}} />
      </Wrapper>,
    );

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /créer le coffre/i }));

    await waitFor(() => {
      expect(screen.getByText(/HARPOCRATE_DEK manquant/i)).toBeInTheDocument();
    });
  });
});
