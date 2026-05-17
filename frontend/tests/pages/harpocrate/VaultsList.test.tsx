import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "@/lib/i18n";
import { VaultsList } from "@/pages/harpocrate/VaultsList";
import * as apiModule from "@/lib/api";
import type { VaultSummary } from "@/lib/harpocrate-vaults.types";

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function makeVault(overrides: Partial<VaultSummary> = {}): VaultSummary {
  return {
    id: "v-1",
    name: "rag",
    label: "Coffre RAG",
    base_url: "https://vault.yoops.org",
    api_key_id: "k-001",
    probe_path: null,
    is_default: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("VaultsList", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    await i18n.changeLanguage("fr");
  });

  it("renders vaults names from the API", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue([
      makeVault({ id: "v-1", name: "rag", label: "Coffre RAG", is_default: true }),
      makeVault({ id: "v-2", name: "staging", label: "Staging", is_default: false }),
    ]);

    render(
      <Wrapper>
        <VaultsList selectedId={null} onSelect={() => {}} onCreate={() => {}} />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText("rag")).toBeInTheDocument();
      expect(screen.getByText("staging")).toBeInTheDocument();
    });
  });

  it("calls onSelect with the vault id when an item is clicked", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue([
      makeVault({ id: "v-42", name: "rag" }),
    ]);
    const onSelect = vi.fn();
    const user = userEvent.setup();

    render(
      <Wrapper>
        <VaultsList selectedId={null} onSelect={onSelect} onCreate={() => {}} />
      </Wrapper>,
    );

    const item = await screen.findByText("rag");
    await user.click(item);
    expect(onSelect).toHaveBeenCalledWith("v-42");
  });

  it("triggers onCreate when clicking the +Nouveau button", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue([]);
    const onCreate = vi.fn();
    const user = userEvent.setup();

    render(
      <Wrapper>
        <VaultsList selectedId={null} onSelect={() => {}} onCreate={onCreate} />
      </Wrapper>,
    );

    await user.click(await screen.findByRole("button", { name: /nouveau/i }));
    expect(onCreate).toHaveBeenCalled();
  });
});
