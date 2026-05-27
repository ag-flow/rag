import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "@/lib/i18n";
import { RetireVaultDialog } from "@/pages/harpocrate/RetireVaultDialog";
import * as apiModule from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { VaultSummary } from "@/lib/harpocrate-vaults.types";

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const vault: VaultSummary = {
  id: "v-1",
  name: "rag",
  label: "Coffre RAG",
  base_url: "https://vault.yoops.org",
  api_key_id: "k-001",
  probe_path: null,
  is_default: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("RetireVaultDialog", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    await i18n.changeLanguage("fr");
  });

  it("keeps the submit button disabled until the typed name matches", async () => {
    const user = userEvent.setup();

    render(
      <Wrapper>
        <RetireVaultDialog
          vault={vault}
          walletName={null}
          open={true}
          onOpenChange={() => {}}
          onRetired={() => {}}
        />
      </Wrapper>,
    );

    const submit = screen.getByRole("button", { name: /retirer le coffre/i });
    expect(submit).toBeDisabled();

    const input = screen.getByPlaceholderText("rag");
    await user.type(input, "wrong");
    expect(submit).toBeDisabled();

    await user.clear(input);
    await user.type(input, "rag");
    expect(submit).toBeEnabled();
  });

  it("calls api.delete and onRetired when the name matches", async () => {
    const deleteSpy = vi.spyOn(apiModule.api, "delete").mockResolvedValue(undefined);
    const onRetired = vi.fn();
    const onOpenChange = vi.fn();
    const user = userEvent.setup();

    render(
      <Wrapper>
        <RetireVaultDialog
          vault={vault}
          walletName="wallet-rag"
          open={true}
          onOpenChange={onOpenChange}
          onRetired={onRetired}
        />
      </Wrapper>,
    );

    await user.type(screen.getByPlaceholderText("rag"), "rag");
    await user.click(screen.getByRole("button", { name: /retirer le coffre/i }));

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith("/api/admin/harpocrate-vaults/v-1");
      expect(onRetired).toHaveBeenCalled();
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it("does not call onRetired when the backend returns HTTP 409", async () => {
    const deleteSpy = vi.spyOn(apiModule.api, "delete").mockRejectedValue(
      new ApiError(409, { detail: "default_vault_cannot_be_retired" }),
    );
    const onRetired = vi.fn();
    const onOpenChange = vi.fn();
    const user = userEvent.setup();

    render(
      <Wrapper>
        <RetireVaultDialog
          vault={vault}
          walletName={null}
          open={true}
          onOpenChange={onOpenChange}
          onRetired={onRetired}
        />
      </Wrapper>,
    );

    await user.type(screen.getByPlaceholderText("rag"), "rag");
    await user.click(screen.getByRole("button", { name: /retirer le coffre/i }));

    // The DELETE must have been attempted, but the conflict path must keep the
    // dialog open and skip onRetired (toast UX is verified manually).
    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith("/api/admin/harpocrate-vaults/v-1");
    });
    expect(onRetired).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});
