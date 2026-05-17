import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "@/lib/i18n";
import { VaultDetailTab } from "@/pages/harpocrate/VaultDetailTab";
import * as apiModule from "@/lib/api";
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
  is_default: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("VaultDetailTab", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    await i18n.changeLanguage("fr");
  });

  it("renders the form pre-filled with vault values", () => {
    render(
      <Wrapper>
        <VaultDetailTab
          vault={vault}
          onReplaceApiKey={() => {}}
          onReveal={() => {}}
          onRetire={() => {}}
        />
      </Wrapper>,
    );

    // Name input (immuable, disabled) shows the vault name.
    expect(screen.getByDisplayValue("rag")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Coffre RAG")).toBeInTheDocument();
    expect(screen.getByDisplayValue("https://vault.yoops.org")).toBeInTheDocument();
    expect(screen.getByDisplayValue("k-001")).toBeInTheDocument();
  });

  it("invokes the retire/replace/reveal handlers", async () => {
    const onRetire = vi.fn();
    const onReplaceApiKey = vi.fn();
    const onReveal = vi.fn();
    const user = userEvent.setup();

    render(
      <Wrapper>
        <VaultDetailTab
          vault={vault}
          onReplaceApiKey={onReplaceApiKey}
          onReveal={onReveal}
          onRetire={onRetire}
        />
      </Wrapper>,
    );

    await user.click(screen.getByRole("button", { name: /retirer ce coffre/i }));
    expect(onRetire).toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /remplacer la clé/i }));
    expect(onReplaceApiKey).toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /reveal/i }));
    expect(onReveal).toHaveBeenCalled();
  });

  it("calls api.patch when Enregistrer is clicked after editing", async () => {
    const patchSpy = vi
      .spyOn(apiModule.api, "patch")
      .mockResolvedValue({ ...vault, label: "Nouveau libellé" });
    const user = userEvent.setup();

    render(
      <Wrapper>
        <VaultDetailTab
          vault={vault}
          onReplaceApiKey={() => {}}
          onReveal={() => {}}
          onRetire={() => {}}
        />
      </Wrapper>,
    );

    const labelInput = screen.getByDisplayValue("Coffre RAG");
    await user.clear(labelInput);
    await user.type(labelInput, "Nouveau libellé");
    await user.click(screen.getByRole("button", { name: /^enregistrer$/i }));

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith(
        "/api/admin/harpocrate-vaults/v-1",
        expect.objectContaining({ label: "Nouveau libellé" }),
      );
    });
  });
});
